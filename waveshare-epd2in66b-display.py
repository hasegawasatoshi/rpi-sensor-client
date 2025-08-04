import argparse
import logging
import os
from datetime import datetime

import epaper
import redis
import yaml
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf"

logging.basicConfig(
    format="[%(module)s] [%(levelname)s] %(message)s", level=logging.INFO
)
logger = logging.getLogger("RPI-E-ink(epd2in66b)")


class EPaper:
    def __init__(self, module="epd2in66b"):
        self.base_x = 24
        self.base_y = 22
        self.offset_h = 32
        self.adjust_w = 120
        self.border_w = 16

        # Load font
        font_path = CONFIG.get("display").get("font") or DEFAULT_FONT_PATH
        self.font16 = ImageFont.truetype(
            os.path.join(os.path.dirname(font_path), os.path.basename(font_path)), 16
        )
        self.font24 = ImageFont.truetype(
            os.path.join(os.path.dirname(font_path), os.path.basename(font_path)), 24
        )
        logger.info(f"Load font: {font_path})")

        # Initialize E-ink paper
        self.epd = epaper.epaper(module).EPD()
        self.epd.init()
        # self.Clear()
        logger.info(f"Initialize E-Paper ({module})")

    def draw(self, tempareture, humidity, co2):
        logger.debug(
            f"Create disply image: tempareture = {tempareture}, humidity = {humidity}, co2 = {co2}"
        )

        # Draw ambiant data
        HBlackimage = Image.new("1", (self.epd.height, self.epd.width), 255)  # 296*152
        drawblack = ImageDraw.Draw(HBlackimage)

        drawblack.rectangle((0, 0, self.epd.height, self.epd.width), fill=255)
        drawblack.text((self.base_x, self.base_y), "CO2", font=self.font24, fill=0)
        drawblack.text(
            (self.base_x, self.base_y + self.offset_h), "気温", font=self.font24, fill=0
        )
        drawblack.text(
            (self.base_x, self.base_y + self.offset_h * 2),
            "湿度",
            font=self.font24,
            fill=0,
        )
        drawblack.text(
            (self.base_x, self.base_y + self.offset_h * 3),
            "更新",
            font=self.font16,
            fill=0,
        )

        text = "%d ppm" % co2 if co2 else "? ppm"
        length = drawblack.textlength(text, font=self.font24)
        drawblack.text(
            (self.epd.width - length + self.adjust_w, self.base_y),
            text,
            font=self.font24,
            fill=0,
        )

        text = "%.1f ℃" % tempareture if tempareture else "? ℃"
        length = drawblack.textlength(text, font=self.font24)
        drawblack.text(
            (self.epd.width - length + self.adjust_w, self.base_y + self.offset_h),
            text,
            font=self.font24,
            fill=0,
        )

        text = "%.1f ％" % humidity if humidity else "? ％"
        length = drawblack.textlength(text, font=self.font24)
        drawblack.text(
            (self.epd.width - length + self.adjust_w, self.base_y + self.offset_h * 2),
            text,
            font=self.font24,
            fill=0,
        )

        current_time = datetime.now()
        text = current_time.strftime("%Y年%m月%d日 %H:%M")
        length = drawblack.textlength(text, font=self.font16)
        drawblack.text(
            (self.epd.width - length + self.adjust_w, self.base_y + self.offset_h * 3),
            text,
            font=self.font16,
            fill=0,
        )

        # Draw border in red
        HRYimage = Image.new(
            "1", (self.epd.height, self.epd.width), 255
        )  # 296*152  ryimage: red or yellow image
        drawry = ImageDraw.Draw(HRYimage)
        drawry.rectangle((0, 0, self.epd.height, self.epd.width), fill=0)
        drawry.rectangle(
            (
                self.border_w,
                self.border_w,
                self.epd.height - self.border_w,
                self.epd.width - self.border_w,
            ),
            fill=255,
        )

        # Display image
        logger.debug("Draw disply image")
        self.epd.display(self.epd.getbuffer(HBlackimage), self.epd.getbuffer(HRYimage))
        logger.debug("Updated")


class Redis:
    def __init__(self, host, port, db):
        self._conn = redis.StrictRedis(
            host=host, port=port, db=db, decode_responses=True
        )

    def read(self, key):
        try:
            return self._conn.get(key)
        except redis.exceptions.ConnectionError as e:
            logger.error(f"{e}")
            raise e


def _int(v):
    try:
        return int(v)
    except (ValueError, TypeError) as e:
        logger.error(f"{e}")
        return None


def _float(v, digits=1):
    try:
        return round(float(v), digits)
    except (ValueError, TypeError) as e:
        logger.error(f"{e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", help="enable debug log", action="store_true")
    parser.add_argument("-c", "--config", default="config.yaml")
    args = parser.parse_args()

    if args.debug:
        logger.info("Enable debug log.")
        logging.getLogger().setLevel(logging.DEBUG)

    with open(args.config) as file:
        global CONFIG
        CONFIG = yaml.safe_load(file.read())
        logger.debug("Configuration: {0}".format(CONFIG))

    logger.info("Start updating e-paper.")
    display = EPaper()
    db = Redis(
        host=CONFIG.get("redis").get("host"),
        port=CONFIG.get("redis").get("port"),
        db=CONFIG.get("redis").get("db"),
    )
    co2 = _int(db.read("co2"))
    temperature = db.read("temperature")
    humidity = db.read("humidity")
    logger.debug(
        f"Readings from redis: temperature = {temperature}, humidity = {humidity}, co2 = {co2}"
    )

    display.draw(_float(temperature), _float(humidity), _int(co2))
    logger.info("Updating e-paper has been done.")


if __name__ == "__main__":
    main()
