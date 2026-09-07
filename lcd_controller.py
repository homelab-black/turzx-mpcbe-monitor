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

import time

from library.lcd.lcd_comm_rev_a import LcdCommRevA

class LcdController:
    def __init__(self, com_port: str, display_width: int, display_height: int):
        """ LCDコントローラーのインスタンスを初期化し、LCDの通信を設定 """
        self.lcd_comm = LcdCommRevA(com_port=com_port,
                                    display_width=display_width,
                                    display_height=display_height)
        self.lcd_comm.InitializeComm()
        self.canvas_width = display_width
        self.canvas_height = display_height

    # 指定されたファイル名のビットマップ画像をLCDに表示します。
    def display_bitmap(self, filename: str):
        self.lcd_comm.DisplayBitmap(filename)

    def display_text(self, text: str, x: int, y: int, height: int, font: str, font_size: int, font_color: tuple, background_color: tuple):
        """ 指定されたテキストをLCDに表示する。文字の位置、フォント、サイズ、色などを設定可能。事前に表示領域を指定された高さで塗りつぶす """
        try:
            self.lcd_comm.DisplayProgressBar(x=x, y=y + 1,
                                             width=(self.canvas_width - x), height=height + 1,
                                             min_value=0, max_value=100, value=100,
                                             bar_outline=False, background_color=background_color)
        except Exception as e:
            print(f"Error displaying progress bar: {e}")

        self.lcd_comm.DisplayText(text, x=x, y=y,
                                  font=font,
                                  font_size=font_size,
                                  font_color=font_color,
                                  background_color=background_color)


    def display_progress_bar(self, x: int, y: int, width: int, height: int, min_value: int, max_value: int, value: int, bar_color: tuple, bar_outline: bool, background_color: tuple):
        """ 指定されたパラメータに基づいてLCDに進行バーを表示。バーの位置、サイズ、範囲、値、色などを設定で可能 """
        self.lcd_comm.DisplayProgressBar(x=x, y=y,
                                         width=width, height=height,
                                         min_value=min_value, max_value=max_value, value=value,
                                         bar_color=bar_color, bar_outline=bar_outline, background_color=background_color)

    def reset(self):
        """ LCDの通信をリセット """
        self.lcd_comm.closeSerial
        time.sleep(1.0)
        self.lcd_comm.Reset()
