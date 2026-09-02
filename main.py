
# 必要なライブラリをインポート
from library.lcd.lcd_comm import Orientation
from library.lcd.lcd_comm_rev_a import LcdCommRevA
import requests
from bs4 import BeautifulSoup
import psutil
#from mutagen.mp3 import MP3
#from mutagen.flac import FLAC
#from mutagen.id3 import ID3, APIC
import music_tag
import math
from PIL import Image, ImageDraw, ImageFont
import os
import io
import hashlib
from dataclasses import dataclass
import math
import time
import shutil
from pathlib import Path
import random
from itertools import chain
import sys
import signal

# グローバル変数の定義
isConnectableMPCBE = False
strHostnameMPCBE = "127.0.0.1"
intPortMPCBE = 13579
intCanvasWidth = 320
intCanvasHeight = 480
isChangePicture = False
isChangeMusic = False
strPictureHash = ""
strPictureFilename = ""
strWorkDirname = "tmp"
strDefaulPictures = "default_png"
strMPCBE_Filepath = ""
intMPCBE_Position = 0
intMPCBE_Duration = 0
intMPCBE_status = 0

@dataclass
class TagInfo:
    strFilepath: str
    strFileExtension: str
    strTitle: str
    strArtist: str
    strAlbum: str
    intLength: int

tagInfo = TagInfo("", "", "", "", "", 0)

# MPCBE が Web サービスが起動しているかをチェックする
def checkMPCBEListen() -> requests.session:

    session = requests.Session()
    global isConnectableMPCBE
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr.port == intPortMPCBE and conn.status == psutil.CONN_LISTEN:
            isConnectableMPCBE = True
            return session
    isConnectableMPCBE = False
    session.close()
    return None


# MPCBE から開いているファイルの情報を取得する
def getMPCBE_variables(session):
    if isConnectableMPCBE == False:
        return

    url = "http://" + strHostnameMPCBE + ":" + str(intPortMPCBE) + "/variables.html"
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"URL の取得に失敗しました: {e}")
        return

    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    global strMPCBE_Filepath
    global isChangeMusic
    global intMPCBE_Position
    global intMPCBE_Duration
    global intMPCBE_status

    p_tag = soup.find("p", id = "filepath")
    if strMPCBE_Filepath != p_tag.get_text(strip=True):
        strMPCBE_Filepath = p_tag.get_text(strip=True)
        isChangeMusic = True
    p_tag = soup.find("p", id = "state")
    intMPCBE_status = (int)(p_tag.get_text(strip=True))
    p_tag = soup.find("p", id = "position")
    intMPCBE_Position = (int)(p_tag.get_text(strip=True))
    p_tag = soup.find("p", id = "duration")
    intMPCBE_Duration = (int)(p_tag.get_text(strip=True))

def create_background(picture) -> bytes:
    # 画像が無い場合は同一ディレクトリに *cover*.jpg または *cover*.png が無いかを検索する
    if picture == None:
        current_file = Path(strMPCBE_Filepath)
        png_files = current_file.parent.glob("*cover*.png")
        jpg_files = current_file.parent.glob("*cover*.jpg")
        jpeg_files = current_file.parent.glob("*cover*.jpeg")
        target_picture = next(chain(png_files, jpg_files, jpeg_files), None)

        # 同一ディレクトリに画像が無ければデフォルト背景からランダムに選択する
        if target_picture == None:
            dir_path = Path(strDefaulPictures)
            files = [p for p in dir_path.iterdir() if p.is_file()]
            if files:
                target_picture = random.choice(files)
            else:
                print('デフォルト背景が選択できませんでした')
        with open(target_picture, 'rb') as f:
            image_bytes = f.read()
            picture_data = image_bytes
    else:
        picture_data = picture.data
    
    # Pillow で画像を開き、リサイズ
    with Image.open(io.BytesIO(picture_data)) as image:
        intShortLength = intCanvasWidth if intCanvasWidth < intCanvasHeight else intCanvasHeight
        image.thumbnail((intShortLength, intShortLength), Image.LANCZOS)

        # 黒で塗りつぶしたキャンバスを用意し、変換した画像を貼り付け、背景イメージとする
        canvas = Image.new("RGB", (intCanvasWidth, intCanvasHeight), (0, 0, 0))
        canvas.paste(image, ((intShortLength - image.width) // 2, (intShortLength- image.height) // 2))

        # 固定文字列を埋め込む
        draw = ImageDraw.Draw(canvas)
        indexX = 4
        indexY = 324
        font = ImageFont.truetype("NotoSansJP-Black.otf", 14)
        draw.text((indexX, indexY), "Title", font=font, fill=(255, 255, 255))
        draw.text((indexX + 44, indexY), " : ", font=font, fill=(255, 255, 255))
        indexY += 20
        draw.text((indexX, indexY), "Artist", font=font, fill=(255, 255, 255))
        draw.text((indexX + 44, indexY), " : ", font=font, fill=(255, 255, 255))
        indexY += 20
        draw.text((indexX, indexY), "Album", font=font, fill=(255, 255, 255))
        draw.text((indexX + 44, indexY), " : ", font=font, fill=(255, 255, 255))
        indexY += 20
        draw.text((indexX, indexY), "Audio", font=font, fill=(255, 255, 255))
        draw.text((indexX + 44, indexY), " : ", font=font, fill=(255, 255, 255))
        indexY += 20
        draw.text((indexX + 44, indexY), " : ", font=font, fill=(255, 255, 255))
        font = ImageFont.truetype("NotoSansJP-Black.otf", 12.5)
        draw.text((indexX, indexY+2), "Length", font=font, fill=(255, 255, 255))

        # メモリ上に背景イメージを書き込む
        png_bytes_io = io.BytesIO()
        canvas.save(png_bytes_io, format="PNG")

        return png_bytes_io.getvalue()


def extract_info():
    ext = os.path.splitext(strMPCBE_Filepath)[1].lower()
    
    picture = None
    global tagInfo
    # 汎用ライブラリで一括読み込み
    try:
        f = music_tag.load_file(strMPCBE_Filepath)
    except Exception:
        print(f"未対応のファイルです。 {strMPCBE_Filepath}")
        global isChangeMusic
        isChangeMusic = False
        return
    
    # 1. 共通タグの取得
    tagInfo.strTitle = str(f['title']) if f['title'] else ''
    tagInfo.strArtist = str(f['artist']) if f['artist'] else ''
    tagInfo.strAlbum = str(f['album']) if f['album'] else ''
    tagInfo.strFileExtension = ext.replace('.', '').upper()
    
    # 2. 共通プロパティの取得
    tagInfo.fltSampleRate = round(float(f.mfile.info.sample_rate) / 1000, 1)
    tagInfo.fltBitrate = round(float(f.mfile.info.bitrate) / 1000, 1)
    tagInfo.intLength = math.ceil(float(f.mfile.info.length))
    
    # 3. ビット深度（BitsPerSample）の判定処理
    # FLACやALACのように、オブジェクトが該当属性を持っていて、かつ値が取得できる場合のみ代入
    if hasattr(f.mfile.info, 'bits_per_sample') and f.mfile.info.bits_per_sample:
        tagInfo.intBitsPerSample = int(f.mfile.info.bits_per_sample)
    else:
        # MP3や通常のM4A(AAC)など、ビット深度の概念がない場合は None
        tagInfo.intBitsPerSample = None
        
    # 4. カバーアート画像の抽出 (music-tagが自動で最適な1枚を選別)
    picture = None
    if f['artwork']:
        picture = f['artwork'].value  # picture.data にバイナリが入る

    # 画像の加工
    if isChangeMusic:
        picture_bytes_io = create_background(picture)

        # 画像のハッシュ値の取得
        hash = hashlib.md5(picture_bytes_io).hexdigest()

        global strPictureFilename
        global strPictureHash
        global isChangePicture
        if strPictureHash != hash:
            # 過去の画像ファイルが有ったら削除する
            if os.path.exists(strPictureFilename):
                try:
                    os.remove(strPictureFilename)
#                    print(f"file removed: {strPictureFilename}")
                except:
                    print(f"Failed file remove: {strPictureFilename}")
            strPictureFilename = strWorkDirname + "/" + hash + ".png"
            strPictureHash = hash
            isChangePicture = True
            # 画像の保存
            with open(strPictureFilename, "wb") as f:
                f.write(picture_bytes_io)

def draw_music_info(lcd_comm, strText, indexX, indexY, spanY):
    lcd_comm.DisplayProgressBar(x=indexX, y=indexY, 
                                width=(intCanvasWidth - indexX), height=(spanY -1), 
                                min_value=0, max_value=100, value=100, 
                                bar_outline=False, background_color=(0,0,0))

    lcd_comm.DisplayText(strText, x=indexX, y=indexY,
                        font="NotoSansJP-Black.otf",
                        font_size=14,
                        font_color=(255, 255, 255),
                        background_color=(0, 0, 0))



def main():
    # MPC-BEに接続可能かをチェックする関数を非同期で実行する
    lcd_comm = LcdCommRevA(com_port="AUTO",
                          display_width=intCanvasWidth,
                          display_height=intCanvasHeight)
    
    # Send initialization commands
    lcd_comm.InitializeComm()
    #lcd_comm.Reset()
    #lcd_comm.Clear()

    # ワークディレクトリの再作成を行う
    dir_path = Path(strWorkDirname)
    if dir_path.exists():
        shutil.rmtree(strWorkDirname)
    dir_path.mkdir(parents=True, exist_ok=True)

    global isChangeMusic
    global isChangePicture
    session = requests.session()
    strTitle = ""
    strArtist = ""
    strAlbum = ""
    strAudio = ""
    strLength = ""
    try:
        while True:
            if not isConnectableMPCBE:
                session = checkMPCBEListen()
            if session == None:
                time.sleep(5)
                continue
            
            getMPCBE_variables(session)
            extract_info()
            if isChangeMusic:
                if intMPCBE_Duration == 0:
                    #普通はあり得ないですが、曲の切り替わりのタイミングで 0 になっている場合は曲情報が取得できていな可能性が高いので、少し時間をおいて再取得する
                    time.sleep(1.0)
                    getMPCBE_variables(session)
                if isChangePicture:
                    lcd_comm.DisplayBitmap(strPictureFilename)
                    #大量データを送信後のため、バッファ溢れのためのWait処理を追加(バッファ溢れを起こすと画面がおかしくなる)
                    time.sleep(0.2)
                    isChangePicture = False

                # Display custom text with solid background
                indexX = 4
                indexY = 324
                if strTitle != tagInfo.strTitle:
                    strTitle = tagInfo.strTitle
                    draw_music_info(lcd_comm, strTitle, indexX + 54, indexY, 20)
                indexY += 20


                if strArtist != tagInfo.strArtist:
                    strArtist = tagInfo.strArtist
                    draw_music_info(lcd_comm, strArtist, indexX + 54, indexY, 20)
                indexY += 20

                if strAlbum != tagInfo.strAlbum:
                    strAlbum = tagInfo.strAlbum
                    draw_music_info(lcd_comm, strAlbum, indexX + 54, indexY, 20)
                indexY += 20

                strAudio_tmp = f"{tagInfo.strFileExtension}, {tagInfo.fltSampleRate} Khz, {f'{tagInfo.intBitsPerSample} bit, ' if tagInfo.intBitsPerSample is not None else ''}{tagInfo.fltBitrate} kbit/s"
                if strAudio != strAudio_tmp:
                    strAudio = strAudio_tmp
                    draw_music_info(lcd_comm, strAudio, indexX + 54, indexY, 20)
                indexY += 20

                strLength_tmp = f"{(tagInfo.intLength // 60)} min {(tagInfo.intLength % 60)}  sec"
                if strLength != strLength_tmp:
                    strLength = strLength_tmp
                    draw_music_info(lcd_comm, strLength, indexX + 54, indexY, 20)
                indexY += 40
                isChangeMusic = False
            
            if intMPCBE_Duration != intMPCBE_Position:
                intAssume_Position = intMPCBE_Position
                startTime = time.time()
                try:
                    while time.time() < (startTime + 5.0):
                        lcd_comm.DisplayProgressBar(x=indexX, y=indexY,
                                                    width=(intCanvasWidth - 8), height=10,
                                                    min_value=0, max_value=intMPCBE_Duration, value=intAssume_Position,
                                                    bar_color=(64, 64, 64), bar_outline=True,
                                                    background_color=(0, 0, 0))
                        if intMPCBE_status == 2:
                            intAssume_Position = intMPCBE_Position + (int)((time.time() - startTime) * 1000)
                            if intAssume_Position <= intMPCBE_Duration:
                                time.sleep(0.5)
                            elif intMPCBE_Duration < intAssume_Position:
                                time.sleep(0.5)
                                break
                        else:
                            time.sleep(1.0)
                except Exception:
                    print(f"進捗バーの表示でエラー？ Duration : {intMPCBE_Duration} , Position: {intMPCBE_Position}, AssumePosition: {intAssume_Position}")
            else:
                time.sleep(5.0)
    finally:
        session.close()
        lcd_comm.Reset()


def mpcbe_abort_handler(signum, frame) -> None:
    print("\n[INFO] OSよりCtrl+Cの割り込みを検出。即座にプロセスを強制終了します。")
    sys.exit(0)

# メイン関数を呼び出す
if __name__ == "__main__":
    signal.signal(signal.SIGINT, mpcbe_abort_handler)
    try:
        # メイン関数を呼び出す
        main()
    except KeyboardInterrupt:
        # Ctrl + C が押されたら、スリープの途中でもここへワープしてくる
        print("\n[INFO] Ctrl+C を検知しました。プログラムを安全に終了します。")
        
        # もし液晶ライブラリの切断関数（例: lcd_comm.close() など）があればここで呼ぶ
        # lcd_comm.close()
        
    except Exception as e:
        # その他の予期せぬエラー用
        print(f"\n[ERROR] 予期せぬエラーが発生しました: {e}")

