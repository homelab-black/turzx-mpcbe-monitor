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

import requests
import shutil
import signal
import sys
import time
from pathlib import Path

from mpcbe_monitor import MpcbeHandler
from lcd_controller import LcdController

def main():
    """ メイン処理 """
    mpcbe_handler = MpcbeHandler(hostname="127.0.0.1", port=13579, work_dirname="tmp", default_pictures="default_png")
    lcd_controller = LcdController(com_port="AUTO", display_width=320, display_height=480)

    # ワークディレクトリの再作成
    dir_path = Path(mpcbe_handler.work_dirname)
    if dir_path.exists():
        shutil.rmtree(mpcbe_handler.work_dirname)
    dir_path.mkdir(parents=True, exist_ok=True)

    # メインループ
    session = requests.session()
    title = ""
    artist = ""
    album = ""
    audio = ""
    length = ""
    lyrics = ""
    cue_index = -1
    assume_position = 0
    is_preloop_has_lyrics = False
    try:
        while True:
            if not mpcbe_handler.is_connectable_mpcbe:
                session = mpcbe_handler.check_mpcbe_listen()
            if session is None:
                time.sleep(5)
                continue

            mpcbe_handler.get_mpcbe_variables(session)
            start_time = time.time()

            if mpcbe_handler.is_have_cue:
                mpcbe_handler.is_change_music = True
                
            if mpcbe_handler.is_change_music:
                index_x = 4
                index_y = 430
                assume_position = mpcbe_handler.mpcbe_position
                lyrics_index = -1
                mpcbe_handler.extract_info()
                if mpcbe_handler.mpcbe_duration == 0:
                    # duration が 0 というのは通常あり得ないので、再読み込みを実施する
                    time.sleep(1.0)
                    mpcbe_handler.get_mpcbe_variables(session)
                    start_time = time.time()
                if mpcbe_handler.is_have_cue:
                    # 曲が変わったかを判定する
                    cue_old_index = cue_index
                    cue_index = mpcbe_handler.find_current_index(assume_position, mpcbe_handler.cue_info)
                    if cue_old_index == cue_index:
                        mpcbe_handler.is_change_picture = False
                if mpcbe_handler.is_change_picture:
                    lcd_controller.display_bitmap(mpcbe_handler.picture_filename)
                    time.sleep(0.2)
                if not mpcbe_handler.is_have_lyrics and is_preloop_has_lyrics:
                    # 直前の曲が歌詞があり、今回は無い場合歌詞表示時のプログレスバーのごみが残らないようにする
                    lcd_controller.display_progress_bar(x=0, y=index_y,
                                                        width=lcd_controller.canvas_width, height=50,
                                                        min_value=0, max_value=100, value=100,
                                                        bar_color=(0, 0, 0), bar_outline=False, background_color=(0, 0, 0))
                    is_preloop_has_lyrics = False
                if mpcbe_handler.is_have_lyrics:
                    lcd_controller.display_progress_bar(x=0, y=index_y,
                                                        width=lcd_controller.canvas_width, height=50,
                                                        min_value=0, max_value=100, value=100,
                                                        bar_color=(0, 0, 0), bar_outline=False, background_color=(0, 0, 0))
                    lcd_controller.display_progress_bar(x=0, y=450,
                                                        width=lcd_controller.canvas_width, height=1,
                                                        min_value=0, max_value=100, value=100,
                                                        bar_color=(192, 192, 192), bar_outline=False, background_color=(0, 0, 0))
                    is_preloop_has_lyrics = True
                        
                index_y = 324
                if mpcbe_handler.is_have_cue:
                    next_title = mpcbe_handler.cue_info[cue_index][1]["title"]
                else:
                    next_title = mpcbe_handler.tag_info.title
                if title != next_title:
                    title = next_title
                    lcd_controller.display_text(title, index_x + 55, index_y, 20, font="NotoSansJP-Regular.otf", font_size=14, font_color=(255, 255, 255), background_color=(0, 0, 0))
                index_y += 20

                if mpcbe_handler.is_have_cue:
                    next_artist = mpcbe_handler.cue_info[cue_index][1]["artist"]
                else:
                    next_artist = mpcbe_handler.tag_info.artist
                if artist != next_artist:
                    artist = next_artist
                    lcd_controller.display_text(artist, index_x + 55, index_y, 20, font="NotoSansJP-Regular.otf", font_size=14, font_color=(255, 255, 255), background_color=(0, 0, 0))
                index_y += 20

                next_album = mpcbe_handler.tag_info.album
                if album != next_album:
                    album = next_album
                    lcd_controller.display_text(album, index_x + 55, index_y, 20, font="NotoSansJP-Regular.otf", font_size=14, font_color=(255, 255, 255), background_color=(0, 0, 0))
                index_y += 20

                audio_parts: list[str] = [
                    f"{mpcbe_handler.tag_info.file_extension}",
                    f"{mpcbe_handler.tag_info.sample_rate} Khz",
                ]
                if mpcbe_handler.tag_info.bits_per_sample is not None:
                    audio_parts.append(f"{mpcbe_handler.tag_info.bits_per_sample} bit")
                if mpcbe_handler.tag_info.bitrate is not None:
                    audio_parts.append(f"{mpcbe_handler.tag_info.bitrate} kbit/s")
                audio_tmp: str = ", ".join(audio_parts)

                if audio != audio_tmp:
                    audio = audio_tmp
                    lcd_controller.display_text(audio, index_x + 55, index_y, 20, font="NotoSansJP-Regular.otf", font_size=14, font_color=(255, 255, 255), background_color=(0, 0, 0))
                index_y += 20

                length_tmp = f"{(mpcbe_handler.tag_info.length // 60)} min {(mpcbe_handler.tag_info.length % 60)}  sec"
                if length != length_tmp:
                    length = length_tmp
                    lcd_controller.display_text(length, index_x + 55, index_y, 20, font="NotoSansJP-Regular.otf", font_size=14, font_color=(255, 255, 255), background_color=(0, 0, 0))
                mpcbe_handler.is_change_music = False
                mpcbe_handler.is_change_picture = False

            if mpcbe_handler.mpcbe_duration != mpcbe_handler.mpcbe_position:
                if mpcbe_handler.is_have_lyrics:
                    index_y = 430
                else:
                    index_y = 445

                # 早送り、巻き戻しの検出
                if abs(mpcbe_handler.mpcbe_position - assume_position) > 5 * 1000 * 2:
                    lyrics_index = -1

                assume_position = mpcbe_handler.mpcbe_position
                try:
                    while time.time() < (start_time + 5):
                        lcd_controller.display_progress_bar(x=0, y=index_y,
                                                            width=lcd_controller.canvas_width, height=10,
                                                            min_value=0, max_value=mpcbe_handler.mpcbe_duration, value=assume_position,
                                                            bar_color=(64, 64, 64), bar_outline=True,
                                                            background_color=(0, 0, 0))
                        if mpcbe_handler.mpcbe_status != 2:
                            time.sleep(0.5)
                            lyrics_index = -1
                            continue
                        if mpcbe_handler.is_have_lyrics:
                            for _ in range(50):
                                assume_position = mpcbe_handler.mpcbe_position + (int)((time.time() - start_time) * 1000)
                                if mpcbe_handler.mpcbe_duration < assume_position:
                                    break
                                if lyrics_index == -1:
                                    lyrics_index = mpcbe_handler.find_current_index(assume_position=assume_position, time_list=mpcbe_handler.lyrics)
                                if lyrics_index < len(mpcbe_handler.lyrics) and ((mpcbe_handler.lyrics[lyrics_index][0] - assume_position <= 0) or (mpcbe_handler.lyrics[lyrics_index][0] - assume_position < 50)) :
                                    if lyrics != mpcbe_handler.lyrics[lyrics_index][1]:
                                        lcd_controller.display_text(mpcbe_handler.lyrics[lyrics_index][1], 4, 452, 20, font="NotoSansJP-Regular.otf", font_size=14, font_color=(255, 255, 255), background_color=(0, 0, 0))
                                        lyrics = mpcbe_handler.lyrics[lyrics_index][1]
                                        lyrics_index += 1
                                time.sleep(0.1)
                        else:
                            assume_position = mpcbe_handler.mpcbe_position + (int)((time.time() - start_time) * 1000)
                            if assume_position <= mpcbe_handler.mpcbe_duration:
                                time.sleep(1.0)
                            elif mpcbe_handler.mpcbe_duration < assume_position:
                                break

                except Exception as e:
                    print(f"進捗バーの表示でエラー？ Duration : {mpcbe_handler.mpcbe_duration} , Position: {mpcbe_handler.mpcbe_position}, AssumePosition: {assume_position}, {e}")
            else:
                time.sleep(5.0)
    finally:
        if session:
            session.close()
        lcd_controller.reset()

def mpcbe_abort_handler(signum, frame) -> None:
    print("\n[INFO] OSよりCtrl+Cの割り込みを検出。即座にプロセスを強制終了します。")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, mpcbe_abort_handler)
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C を検知しました。プログラムを安全に終了します。")
    except Exception as e:
        print(f"\n[ERROR] 予期せぬエラーが発生しました: {e}")
