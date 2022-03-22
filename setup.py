# -*-coding:utf-8-*-
"""setup for tg-outline-vpn-bot"""

from setuptools import setup

setup(
    name="tg-outline-vpn-bot",
    version="2.0.0",
    packages=["vpn_bot"],
    url="https://github.com/andreinechaev/tg-outline-vpn-bot/",
    license="MIT",
    author="Andrei Nechaev",
    author_email="iphoenix179@gmail.com",
    description="Telegram bot for Outline VPN",
    long_description=open("README.md", "r").read(),
    long_description_content_type="text/markdown",
    install_requires=("requests", "python-telegram-bot",
                      "numpy", "watchdog", "requests-cache"),
)
