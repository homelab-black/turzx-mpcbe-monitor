# Copyright (C) 2026 homelab-black
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://gnu.org>.

import hashlib
import io
import math
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path

import mutagen
import psutil
import requests
import taglib
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

@dataclass
class TagInfo:
    file_extension: str
    title: str
    artist: str
    album: str
    length: int
    sample_rate: float = 0.0
    bitrate: float = 0.0
    bits_per_sample: int = 0


class MpcbeHandler:
    def __init__(self, hostname: str, port: int, work_dirname: str, default_pictures: str):
        """ クラスのインスタンス変数を初期化します。 """
        self.hostname = hostname
        self.port = port
        self.work_dirname = work_dirname
        self.default_pictures = default_pictures
        self.is_connectable_mpcbe = False
        self.mpcbe_filepath = ""
        self.mpcbe_position = 0
        self.mpcbe_duration = 0
        self.mpcbe_status = 0
        self.tag_info = TagInfo("", "", "", "", 0)
        self.is_change_music = False
        self.is_change_picture = False
        self.is_first_run = True
        self.is_have_cue = False
        self.is_have_lyrics = False
        self.picture_hash = ""
        self.picture_filename = ""
        self.lyrics = []
        self.preview_time = -50
        self.cue_info = []

    def check_mpcbe_listen(self) -> requests.Session | None:
        """ MCP-BE のウェブサーバへの接続確認 """
        session = requests.Session()
        for conn in psutil.net_connections(kind="inet"):
            if conn.laddr.port == self.port and conn.status == psutil.CONN_LISTEN:
                self.is_connectable_mpcbe = True
                print(f"MPC-BEに接続可能なため処理を開始します。")
                return session
        self.is_connectable_mpcbe = False
        session.close()
        return None

    def get_mpcbe_variables(self, session):
        """ MPC-BEから開いているファイルの情報を取得し、クラス変数を更新する """
        if not self.is_connectable_mpcbe:
            return

        url = f"http://{self.hostname}:{self.port}/variables.html"
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"URL の取得に失敗しました。MPC-BEに再接続可能になるまで待機します。 {e}")
            self.is_connectable_mpcbe = False
            return

        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        p_tag = soup.find("p", id="filepath")
        if self.mpcbe_filepath != p_tag.get_text(strip=True):
            self.mpcbe_filepath = p_tag.get_text(strip=True)
            self.is_change_music = True
        p_tag = soup.find("p", id="state")
        self.mpcbe_status = int(p_tag.get_text(strip=True))
        p_tag = soup.find("p", id="position")
        self.mpcbe_position = int(p_tag.get_text(strip=True))
        p_tag = soup.find("p", id="duration")
        self.mpcbe_duration = int(p_tag.get_text(strip=True))

    def extract_info(self):
        """ ファイルから各種情報を取得する """
        picture = None
        try:
            tag_info = taglib.File(self.mpcbe_filepath)
        except Exception:
            print(f"taglib未対応のファイルです。 {self.mpcbe_filepath}")
            self.tag_info.title = "Not Support Format"
            self.tag_info.artist = "Not Support Format"
            self.tag_info.album = "Not Support Format"
            self.tag_info.file_extension = (Path(self.mpcbe_filepath).suffix[1:]).upper()
            return
        
        self.tag_info.title = tag_info.tags["TITLE"][0] if ("TITLE" in tag_info.tags) else "Undefined Title"
        self.tag_info.artist = tag_info.tags["ARTIST"][0] if ("ARTIST" in tag_info.tags) else "Undefined Artist"
        self.tag_info.album = tag_info.tags["ALBUM"][0] if ("ALBUM" in tag_info.tags) else "Undefined Album"
        self.tag_info.file_extension = (Path(self.mpcbe_filepath).suffix[1:]).upper()

        try:
            audio_info = mutagen.File(self.mpcbe_filepath).info
        except Exception:
            self.tag_info.sample_rate = None
            self.tag_info.bitrate = None
            self.tag_info.length = math.ceil(self.mpcbe_duration / 1000)
            self.tag_info.bits_per_sample = None
            print(f"mutagen未対応のファイルです。 {self.mpcbe_filepath}")
        
        self.tag_info.sample_rate = round(float(audio_info.sample_rate) / 1000, 1) if hasattr(audio_info, "sample_rate") else None
        self.tag_info.bitrate = round(float(audio_info.bitrate) / 1000, 1) if hasattr(audio_info, "bitrate") else None
        self.tag_info.length = math.ceil(audio_info.length) if hasattr(audio_info, "length") else math.ceil(self.mpcbe_duration / 1000)
        self.tag_info.bits_per_sample = audio_info.bits_per_sample if hasattr(audio_info, "bits_per_sample") else None
        if self.tag_info.bits_per_sample != None and self.tag_info.bits_per_sample == 0:
            # mutagen で取得したbitrateが0の場合は表示させないようにする
            self.tag_info.bits_per_sample = None

        # cue ファイルの存在チェック
        filepath = Path(self.mpcbe_filepath)
        cue_path = filepath.with_suffix(".cue")
        tag_cue_path = filepath.with_name(filepath.stem + "_tag.cue")
        if cue_path.exists():
            self.is_have_cue = True
            self.read_cuefile(cue_path)
        elif tag_cue_path.exists():
            self.is_have_cue = True
            self.read_cuefile(tag_cue_path)
        else:
            self.is_have_cue = False

        if self.is_change_music:
            # 歌詞の読み込み(曲データまたは歌詞データがあれば)
            if "LYRICS" in tag_info.tags:
                self.read_lyrics(tag_info.tags["LYRICS"][0])
                if len(self.lyrics) != 0:
                    self.is_have_lyrics = True
            else:
                self.check_lyrics()

            # 画像データの読み込み(存在しなければNone)
            if tag_info.pictures:
                index_tmp = -1

                for i, art in enumerate(tag_info.pictures):
                    if art.picture_type == "Front Cover":
                        index_tmp = i
                        break
                    if art.picture_type == "Other" and index_tmp == -1:
                        index_tmp = i
                    
                # ・ループが終わって、index_tmp が -1 なら、index を 0、それ以外なら index に index_tmp を代入
                if index_tmp == -1:
                    target_index = 0
                else:
                    target_index = index_tmp
                picture_data = tag_info.pictures[target_index].data

            if not picture:
                current_dir = Path(self.mpcbe_filepath).parent
                # 1回だけフォルダ内をスキャンし、ファイルをリスト化 (NASなどのリモートの場合を見据えてアクセス回数を削減)
                list_files = list(current_dir.iterdir()) if current_dir.is_dir() else []

                # 優先順位順の条件リスト (キーワード, 拡張子)
                # Folder.jpg はキーワードが "folder" で拡張子が ".jpg" と定義
                list_conditions = [
                    ("cover", ".png"),
                    ("cover", ".jpg"),
                    ("cover", ".jpeg"),
                    ("front", ".png"),
                    ("front", ".jpg"),
                    ("front", ".jpeg"),
                    ("folder", ".png"),
                    ("folder", ".jpg"),
                    ("folder", ".jpeg"),
                ]

                # 条件に合致する最初の1枚を特定する
                target_picture = next(
                    (
                        obj_p for str_key, str_suf in list_conditions
                        for obj_p in list_files
                        if (str_key in obj_p.name.lower() and obj_p.suffix.lower() == str_suf)
                        # Folder.jpg の完全一致に対応するため、Folder.jpg の時だけ完全一致にする場合は以下
                        if (str_key == "folder" and obj_p.name.lower() == "folder.jpg") or 
                        (str_key != "folder" and str_key in obj_p.name.lower() and obj_p.suffix.lower() == str_suf)
                    ),
                    None
                )

                if target_picture is None:
                    dir_path = Path(self.default_pictures)
                    files = [p for p in dir_path.iterdir() if p.is_file()]
                    if files:
                        target_picture = random.choice(files)
                    else:
                        print("デフォルト背景が選択できませんでした")
                with open(target_picture, 'rb') as f:
                    image_bytes = f.read()
                    picture_data = image_bytes
                
            # 画像の読み込み
            picture_bytes_io = self.create_background(picture_data)

            hash_value = hashlib.md5(picture_bytes_io).hexdigest()

            if self.picture_hash != hash_value:
                if os.path.exists(self.picture_filename):
                    try:
                        os.remove(self.picture_filename)
                    except:
                        print(f"Failed file remove: {self.picture_filename}")
                self.picture_filename = f"{self.work_dirname}/{hash_value}.png"
                if self.is_first_run:
                    self.is_first_run = False
                else:
                    self.picture_hash = hash_value
                self.is_change_picture = True
                with open(self.picture_filename, "wb") as f:
                    f.write(picture_bytes_io)

    def create_background(self, picture_data) -> bytes:
        """ MPC-BEから取得したタグ情報から背景を描画する """
        with Image.open(io.BytesIO(picture_data)) as image:
            short_length = 320
            orig_w, orig_h = image.size
            if orig_w > orig_h:
                new_w = 320
                new_h = int(orig_h * (320 / orig_w))
            else:
                new_h = 320
                new_w = int(orig_w * (320 / orig_h))
            image = image.resize((new_w, new_h), Image.LANCZOS)

            canvas = Image.new("RGB", (short_length, short_length), (0, 0, 0))
            canvas.paste(image, ((short_length - image.width) // 2, (short_length - image.height) // 2))
            png_bytes_io = io.BytesIO()
            canvas.save(png_bytes_io, format="PNG")

            if self.is_first_run:
                self.picture_hash = hashlib.md5(png_bytes_io.getvalue()).hexdigest()

                canvas = Image.new("RGB", (320, 480), (0, 0, 0))
                canvas.paste(image, ((short_length - image.width) // 2, (short_length - image.height) // 2))

                draw = ImageDraw.Draw(canvas)
                index_x = 4
                index_y = 324
                font = ImageFont.truetype("segoeui.ttf", 14)
                draw.text((index_x, index_y), "Title", font=font, fill=(255, 255, 255))
                draw.text((index_x + 44, index_y), " : ", font=font, fill=(255, 255, 255))
                index_y += 20
                draw.text((index_x, index_y), "Artist", font=font, fill=(255, 255, 255))
                draw.text((index_x + 44, index_y), " : ", font=font, fill=(255, 255, 255))
                index_y += 20
                draw.text((index_x, index_y), "Album", font=font, fill=(255, 255, 255))
                draw.text((index_x + 44, index_y), " : ", font=font, fill=(255, 255, 255))
                index_y += 20
                draw.text((index_x, index_y), "Audio", font=font, fill=(255, 255, 255))
                draw.text((index_x + 44, index_y), " : ", font=font, fill=(255, 255, 255))
                index_y += 20
                draw.text((index_x, index_y), "Length", font=font, fill=(255, 255, 255))
                draw.text((index_x + 44, index_y), " : ", font=font, fill=(255, 255, 255))

                png_bytes_io = io.BytesIO()
                canvas.save(png_bytes_io, format="PNG")

            return png_bytes_io.getvalue()

    def check_lyrics(self):
        """ 音楽ファイルに対応する歌詞ファイルの存在を確認し、有れば、歌詞データの取り込みを呼び出す """
        lyrics_path = Path(self.mpcbe_filepath).with_suffix(".lrc")
        if lyrics_path.exists():
            self.is_have_lyrics = True
        elif (lyrics_path.parent / "Lyrics" / lyrics_path.name).exists():
            lyrics_path = lyrics_path.parent / "Lyrics" / lyrics_path.name
            self.is_have_lyrics = True
        else:
            return

        detected_encoding: str = "utf-8"
        try:
            lyrics_path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            detected_encoding = "cp932"
        with open(lyrics_path, "r", encoding=detected_encoding) as f:
            text = f.read()
            self.read_lyrics(text)


    def read_lyrics(self, lyrics: str):
        """ 歌詞データの取り込み （複数言語の場合は同一時刻で複数行となるがその場合最後の行が優先される。（どの言語を表示すればよいか判断不能）"""
        self.lyrics.clear()
        result = {}
        line_pat = re.compile(r"(\[(?:\d+[:.]\d+(?:\.\d+)?)\])+([^\[]*)")
        tag_pat = re.compile(r"\[(\d+[:.]\d+(?:\.\d+)?)\]")
        for lines in lyrics.splitlines():
            line: str = lines.strip()
            if line:
                line_match = line_pat.match(line.strip())
                if not line_match:
                    continue
                tags_part, lyric = line_match.groups()
                lyric = lyric.strip()
                for tag in tag_pat.findall(tags_part):
                    try:
                        ms = self.timestamp_to_ms(tag)
                    except ValueError as e:
                        continue
                    result[ms] = lyric
        if len(result) != 0:
            self.lyrics = list(sorted(result.items()))

    def read_cuefile(self, cue_filename: Path):
        """ CUEファイルの内容をリスト形式に格納する """
        self.cue_info.clear()

        try:
            with open(cue_filename, "r", encoding="utf-8-sig") as f:
                cue_data = f.read()
        except UnicodeDecodeError:
            with open(cue_filename, "r", encoding="cp932") as f:
                cue_data = f.read()
        # アルバム情報とトラック情報に分割する
        album_info = (cue_data[:cue_data.find("TRACK 01 ") - 1]).strip().splitlines()
        tracks_info = (cue_data[cue_data.find("TRACK 01 "):]).strip().splitlines()
        # アルバム情報の取得
        for line in album_info:
            match line.strip().split(maxsplit=1)[0]:
                case "TITLE":
                    album = line.strip().split(maxsplit=1)[1].strip('"')
                    self.tag_info.album = album if album != "" else "Undefined Album"
                case "PERFORMER":
                    artist = line.strip().split(maxsplit=1)[1].strip('"')
                    self.tag_info.artist = artist if artist != "" else "Undefined Artist"
        # トラック情報の取得
        track_index = 0
        result = {}
        for line in tracks_info:
            match line.strip().split(maxsplit=1)[0]:
                case "TRACK":
                    track_index += 1
                    if track_index != 1:
                        # 曲情報を格納する
                        result[position_index] = {"title":track_title, "artist":track_artist}
                    # 次の曲に向けて値を初期化する
                    track_title = "Undefined Title"
                    track_artist = "Undefined Artist"
                case "TITLE":
                    title = line.strip().split(maxsplit=1)[1].strip('"')
                    track_title = title if title != "" else "Undefined Title"
                case "PERFORMER":
                    artist = line.strip().split(maxsplit=1)[1].strip('"')
                    track_artist = artist if artist != "" else "Undefined Artist"
                case "INDEX":
                    if line.strip().split()[1] == "01":
                        # トラックの始まり位置を ms にする (最後の値はmsではなく、（75 frame/sec）」の値)
                        times = line.strip().split()[2].split(":")
                        position_index = (int(times[0]) * 60 + int(times[1])) * 1000 + int(times[2]) * 1000 // 75
        # 最後の曲の情報を追加する
        result[position_index] = {"title":track_title, "artist":track_artist}
        self.cue_info = list(sorted(result.items()))

    def timestamp_to_ms(self, ts: str) -> int:
        """ LRC形式のタイムスタンプをミリ秒に変換する """
        minute_part, sec_frac = ts.split(":", 1)
        minutes = int(minute_part)

        if "." in sec_frac:
            seconds_str, frac_str = sec_frac.split(".", 1)
        else:
            seconds_str, frac_str = sec_frac, ""

        seconds = int(seconds_str)

        if len(frac_str) == 0:
            millis = 0
        else:
            millis = int(frac_str[:3].ljust(3, "0"))

        return (minutes * 60 + seconds) * 1000 + millis

    def find_current_index(self, assume_position: int, time_list: list[list]) -> int:
        """ 現在の再生位置から、最適なデータのインデックスを返す """
        if not time_list:
            return -1
            
        # 1. もし再生位置が「歌詞の開始時間」よりも前の場合は、先頭(0)を返す
        if assume_position < time_list[0][0]:
            return 0

        # 2. リストを後ろから逆順にスキャンする
        for index in range(len(time_list) - 1, -1, -1):
            if assume_position >= time_list[index][0]:
                return index
        return 0