import argparse
import logging
import signal
import time

import adafruit_scd4x
import board
import redis
import yaml

logging.basicConfig(
    format="[%(module)s] [%(levelname)s] %(message)s", level=logging.INFO
)
logger = logging.getLogger("RPI-SCD4x")


class TerminatedException(Exception):
    pass


def signal_handler(signum, frame):
    logging.info("Catched signal [ %d ]." % (signum))
    raise TerminatedException


class SCD4x:
    def __init__(self):
        self.i2c = board.I2C()
        self.scd4x = adafruit_scd4x.SCD4X(self.i2c)
        logger.info(
            "Serial number: %s" % " ".join([hex(i) for i in self.scd4x.serial_number])
        )
        self.scd4x.start_periodic_measurement()
        logger.info("Start measurement")

    def __del__(self):
        self.scd4x.stop_periodic_measurement()
        logger.info("Stop measurement")

    def read(self):
        if self.scd4x.data_ready:
            return {
                "co2": self.scd4x.CO2,
                "temperature": self.scd4x.temperature,
                "humidity": self.scd4x.relative_humidity,
            }
        return None


class Redis:
    def __init__(self, host, port, db):
        self._conn = redis.StrictRedis(
            host=host, port=port, db=db, decode_responses=True
        )

    def write(self, key, value, ex=10):
        try:
            self._conn.set(key, value, ex)
        except redis.exceptions.ConnectionError as e:
            logger.error(f"{e}")
            raise e


def mainloop(sensor, db):
    try:
        while True:
            readings = sensor.read()
            if readings is not None:
                logger.debug(f"readings = {readings}")
                co2 = readings.get("co2")
                temperature = readings.get("temperature")
                humidity = readings.get("humidity")
                db.write("co2", co2)
                db.write("temperature", temperature)
                db.write("humidity", humidity)
                time.sleep(CONFIG.get("scd4x").get("monitoring").get("intervals"))

    except KeyboardInterrupt:
        logger.error("Stopped by keyboard imput (ctrl-c)")

    except TerminatedException:
        logger.error("Stopded by systemd.")

    except OSError as e:
        import traceback

        traceback.print_exc()
        raise e

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise e

    finally:
        logger.info("Cleanup and stop SCD4x monitoring service.")


if __name__ == "__main__":
    logger.info("Sensirion SCD4x monitoring service started.")
    signal.signal(signal.SIGTERM, signal_handler)

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
        logger.info("Configuration: {0}".format(CONFIG))

    sensor = SCD4x()
    db = Redis(
        host=CONFIG.get("redis").get("host"),
        port=CONFIG.get("redis").get("port"),
        db=CONFIG.get("redis").get("dbname"),
    )
    mainloop(sensor, db)
