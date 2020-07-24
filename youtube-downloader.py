import aiohttp
import asyncio
import re
import json
import os
from functools import partial
import logging
import urllib
from urllib.parse import urlparse
from config import TOKEN

yt = [
    "http://www.youtube.com/",
    "http://youtu.be/",
    "https://youtu.be/",
    "http://s.ytimg.com/",
    "http://i2.ytimg.com/",
    "https://m.youtube.com/",
    "https://www.youtube.com/",
]

USER_AGENT = os.getenv(
    "USER_AGENT", "Mozilla/5.0 (X11; Linux x86_64; rv:75.0) Gecko/20100101 Firefox/75.0"
)

PROXY = os.getenv("PROXY", "")
ODIR = os.getenv("OUTDIR", "/tmp")
URL = "https://api.telegram.org/bot{}".format(TOKEN)

# Ensure input variables don't contain special characters
assert not set(PROXY).intersection("'\"$#`| ")
assert not set(ODIR).intersection("'\"$#`| ")

busy_id = []


TEXT = {
    "start": {
        "fa": "سلام کاربر عزیز\N{Waving Hand Sign}!\nلطفا لینک یوتیوب یا اینستاگرامت رو وارد کن تا من برای دانلود راهنماییت کنم.",
        "en": "Hi my friend \N{Waving Hand Sign}!\nPlease enter your YouTube or Instagram link then I will help you for download",
    },
    "wrong_link": {
        "fa": " متاسفم! شما یک لینک اشتباه وارد کردید.\nلطفا فقط لینکهای یوتیوب یا اینستاگرام معتبر وارد کنید",
        "en": "Sorry! You have entered an invalid link. Please only enter valid YouTube or Instagram links.",
    },
    "downloading": {
        "fa": "\N{Inbox Tray} در حال دانلود. . .",
        "en": "\N{Inbox Tray} Downloading ...",
    },
    "50M_error": {
        "fa": "\N{Cross Mark} حجم ویدئو انتخاب شده بیشتر از 50 مگابایت است.\n لطفا یکی دیگر از فرمت‌ها رو انتخاب کنید",
        "en": "\N{Cross Mark} Size of your selected video is more than 50M. I cannot send files bigger than 50M.\nPlease try another one.",
    },
    "download_failed": {
        "fa": "\N{Cross Mark} دانلود ناموفق! \N{Exclamation Mark}",
        "en": "\N{Cross Mark} Download failed \N{Exclamation Mark}",
    },
    "download_complete": {
        "fa": "دانلود کامل شد!\n فایل شما \N{White Down Pointing Backhand Index}",
        "en": "Download completed!\nThis is your file \N{White Down Pointing Backhand Index}",
    },
    "waiting": {
        "fa": "لطفا صبر کنید \N{smiling face with smiling eyes}\n ما داریم سعی میکنیم که لیست فرمت‌های موجود رو بدست بیاریم.",
        "en": "Please wait \N{smiling face with smiling eyes}\nWe are trying to find all available formats.",
    },
    "list_failed": {
        "fa": "\N{Cross Mark} متاسفانه دسترسی به لیست فرمت‌ها ممکن نیست\N{Exclamation Mark}",
        "en": "\N{Cross Mark} Unable to fetch the format list \N{Exclamation Mark}",
    },
    "all_formats": {"fa": "لیست تمام فرمت‌های موجود:", "en": "All available formats:"},
    "attention": {
        "fa": """\
        \N{pushpin}\N{pushpin}        توجه کنید!       \N{pushpin}\N{pushpin}
        سه نوع لینک برای شما ارسال شده:
        \N{speaker} فقط صدا
        \N{Speaker with Cancellation Stroke} فقط ویدئو
        \N{Movie Camera} ویدئوی با صدا
        """,
        "en": """\
        \N{pushpin}\N{pushpin}        Attention!       \N{pushpin}\N{pushpin}
        There are 3 kind of links:
        \N{speaker} Audio only
        \N{Speaker with Cancellation Stroke} Video only
        \N{Movie Camera} Complete video files (video + audio)
        """,
    },
    "interference": {
        "fa": "\N{Cross Mark} لطفا صبر کنید تا به درخواست قبلی شما رسیدگی کنم. سپس درخواست بعدی را وارد کنید",
        "en": "Sorry! please try again after finish your previous download.",
    },
}
# Logging configuration
# Logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Formatters
f1 = logging.Formatter("%(asctime)s - %(message)s")
f2 = logging.Formatter("%(message)s")

# Handler
sh = logging.StreamHandler()
sh.setFormatter(f2)
sh.setLevel(logging.DEBUG)

fh = logging.FileHandler("log.txt")
fh.setFormatter(f1)
fh.setLevel(logging.INFO)

# Add handler
logger.addHandler(fh)
logger.addHandler(sh)


async def fetch(client, offset):
    r = []

    try:
        async with client.get(
            "{}/getUpdates".format(URL), params={"offset": offset},
        ) as resp:
            if resp.status == 200:
                r = await resp.json()
                r = r["result"]
                clean_r = offset < 0
                offset = offset = r[-1]["update_id"] + 1 if r else 0
                if clean_r:
                    r = []
                return r, offset
            else:
                return [], 0
    except (aiohttp.ClientError, OSError, KeyError) as ex:
        logger.debug("Geting updates is failed: {}".format(ex))
        return [], 0


async def strt(client, id, language):

    try:
        text = TEXT["start"][language]
        async with client.post(
            "{}/sendMessage".format(URL), data={"chat_id": id, "text": text},
        ):
            logger.debug("Send start message to {}".format(id))
    except aiohttp.ClientError as ex:
        logger.debug("Error in sending start message to {}: {}".format(id, ex))


async def undefined(client, id, language):
    text = TEXT["wrong_link"][language]
    try:
        async with client.post(
            "{}/sendMessage".format(URL), data={"chat_id": id, "text": text},
        ):
            logger.debug("{} send an undefined link".format(id))
    except aiohttp.ClientError as ex:
        logger.debug("Error in sending undefined message to {}: {}".format(id, ex))


async def download_ut(client, cmd, id, format, typ, usr_link, language):
    logger.debug("Start downloading {} for {}".format(usr_link, id))
    text = TEXT["downloading"][language]
    try:
        async with client.post(
            "{}/sendMessage".format(URL), data={"chat_id": id, "text": text},
        ) as resp:
            dta = await resp.json()
            m_id = dta["result"]["message_id"]
    except (aiohttp.ClientError, KeyError) as ex:
        logger.debug(
            "Error in send downloading . . . message {} to {}: {}".format(
                usr_link, id, ex
            )
        )
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()

    if not stdout or stderr:
        if b"ERROR: requested format not available\n" in stderr:
            text = TEXT["50M_error"][language]
            try:
                async with client.post(
                    "{}/editMessageText".format(URL),
                    data={"chat_id": id, "text": text, "message_id": m_id},
                ) as resp:
                    logger.debug(
                        "File size > 50M of link: {} for id {}; format {} stderr {}".format(
                            usr_link, id, format, stderr
                        )
                    )
                    return
            except aiohttp.ClientError:
                return

        try:
            text = TEXT["download_failed"][language]
            async with client.post(
                "{}/editMessageText".format(URL),
                data={"chat_id": id, "text": text, "message_id": m_id},
            ) as resp:
                logger.debug(
                    "Failed in download link: {} for id: {} ERROR: {}".format(
                        usr_link, id, stderr
                    )
                )
                return
        except aiohttp.ClientError as ex:
            logger.debug("Error: {}".format(ex))
            return

    try:
        text = TEXT["download_complete"][language]
        async with client.post(
            "{}/editMessageText".format(URL),
            data={"chat_id": id, "text": text, "message_id": m_id},
        ):
            pass
    except aiohttp.ClientError:
        pass

    path = "{}/{}.{}".format(ODIR, id, format)
    files = open(path, "rb")
    if typ == "a":

        try:
            async with client.post(
                "{}/sendChatAction".format(URL),
                data={"chat_id": str(id), "action": "upload_audio"},
            ):
                pass
        except aiohttp.ClientError as ex:
            logger.debug(
                "Error in sending audio_ChatAction to{} for this link: {}: {}".format(
                    id, usr_link, ex
                )
            )

        try:
            async with client.post(
                "{}/sendAudio".format(URL), data={"chat_id": str(id), "audio": files},
            ):
                pass
        except aiohttp.ClientError as ex:
            logger.debug(
                "Error in sending audio_link: {} to {}: {}".format(usr_link, id, ex)
            )
            return
    else:

        try:
            async with client.post(
                "{}/sendChatAction".format(URL),
                data={"chat_id": str(id), "action": "upload_video"},
            ):
                pass
        except aiohttp.ClientError as ex:
            logger.debug(
                "Error in sending video_ChatAction to {} for this link: {}: {}".format(
                    id, usr_link, ex
                )
            )

        try:
            async with client.post(
                "{}/sendVideo".format(URL), data={"chat_id": str(id), "video": files},
            ):
                pass
        except aiohttp.ClientError as ex:
            logger.debug(
                "Error in sending video_link: {} to {}: {}".format(usr_link, id, ex)
            )
            return
    logger.debug("Sending file to {} done".format(id))
    os.remove(path)


def make_keyboard(audio_list, video_list, movie_list):
    inline_keyboard = []
    for x in audio_list:
        cldata = "{} {} {}*a".format(x["format_code"], x["ut_link"], x["format"])
        btn = [{"text": "\N{speaker}  {}".format(x["txt"]), "callback_data": cldata}]
        inline_keyboard.append(btn)
    for x in video_list:
        cldata = "{} {} {}*v".format(x["format_code"], x["ut_link"], x["format"])
        btn = [
            {
                "text": "\N{Speaker with Cancellation Stroke} {}".format(x["txt"]),
                "callback_data": cldata,
            }
        ]
        inline_keyboard.append(btn)
    for x in movie_list:
        cldata = "{} {} {}*m".format(x["format_code"], x["ut_link"], x["format"])
        btn = [
            {"text": "\N{Movie Camera} {}".format(x["txt"]), "callback_data": cldata}
        ]
        inline_keyboard.append(btn)

    return inline_keyboard


def size_tostr(s):
    # This is the formula to convert byte to MiB (byte / 1049653.68 = MiB) and this one for KiB(byte / 1024.00517 = KiB)
    # The number with 3 digit or less stay byte and numbers between 4 to 6 digit convert to KiB and number with 7 to 9 digit change to MiB
    assert_value = s / 2 ** 20
    assert 0 < assert_value <= 50, "Size bigger than 50M"
    if s < 1000:
        size = str(s)
    elif s < 1000000:
        size = s / 2 ** 10
        size = "{:.2f} {}".format(size, "KiB")
    elif s < 1000000000:
        size = s / 2 ** 20
        size = "{:.2f} {}".format(size, "MiB")
    return size


def parse_formats(j, ut_link):
    audio_list = []
    video_list = []
    movie_list = []
    for i in j["formats"]:
        size = i["filesize"] if "filesize" in i else 0
        if size:
            # It means if size of our format is bigger than 50MiB we didn't send it to user
            assert_value = size / 2 ** 20
            if assert_value > 50:
                continue
            else:
                size = size_tostr(size)
        format_code = i["format_id"]
        format = i["ext"]
        height = i["height"] if "height" in i else None
        width = i["width"] if "width" in i else None
        abr = i["abr"] if "abr" in i else None
        asr = i["asr"] if "asr" in i else None
        if not width and not height and asr and abr:
            audio_list.append(
                {
                    "format_code": format_code,
                    "ut_link": ut_link,
                    "format": format,
                    "txt": "AUDIO  {}  {}".format(format, size),
                }
            )
        elif not abr and not asr and width and height:
            video_list.append(
                {
                    "format_code": format_code,
                    "ut_link": ut_link,
                    "format": format,
                    "txt": "VIDEO {} {}".format(format, size),
                }
            )
        elif height and width and abr and asr:
            movie_list.append(
                {
                    "format_code": format_code,
                    "ut_link": ut_link,
                    "format": format,
                    "txt": "MOVIE {} {}".format(format, size),
                }
            )
    return audio_list, video_list, movie_list


async def list_ut(client, cmd, id, ut_link, language):
    logger.debug("Making YT_list of {} for {}".format(ut_link, id))
    text = TEXT["waiting"][language]
    try:
        async with client.post(
            "{}/sendMessage".format(URL), data={"chat_id": id, "text": text},
        ) as resp:
            dta = await resp.json()
            m_id = dta["result"]["message_id"]
    except (aiohttp.ClientError, KeyError):
        logger.debug(
            "Error in send message to {} before make YT_list of: {}".format(id, ut_link)
        )
        return

    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if stderr:
        logger.debug("stderr (id: {}): {}".format(id, stderr))

    if not stdout or stderr:
        logger.debug(
            "Unable to fetch the list of formats: link {}; id {}; err {}".format(
                ut_link, id, stderr
            )
        )

        try:
            text = TEXT["list_failed"][language]
            async with client.post(
                "{}/editMessageText".format(URL),
                data={"chat_id": id, "text": text, "message_id": m_id},
            ):
                return
        except aiohttp.ClientError:
            return
    j = json.loads(stdout)
    logger.debug("Successfully made the list for {}".format(ut_link))
    text = TEXT["all_formats"][language]
    audio_list, video_list, movie_list = parse_formats(j, ut_link)
    inline_keyboard = make_keyboard(audio_list, video_list, movie_list)
    reply_markup = {"inline_keyboard": inline_keyboard}
    reply_markups = json.dumps(reply_markup)
    kbd = {
        "chat_id": id,
        "text": text,
        "reply_markup": reply_markups,
        "message_id": m_id,
    }
    try:
        async with client.post("{}/editMessageText".format(URL), data=kbd) as resp:
            if resp.status == 200:
                logger.debug("Send keyboard of list to {} successful".format(id))
    except aiohttp.ClientError as ex:
        logger.debug(
            "Error in sending keyboard of this link: {} to id: {} Exception: {}".format(
                ut_link, id, ex
            )
        )
        return
    try:
        text = TEXT["attention"][language]
        async with client.post(
            "{}/sendMessage".format(URL), data={"chat_id": id, "text": text},
        ):
            pass
    except aiohttp.ClientError:
        pass


def nothing(req, id, client):
    pass


def req_process(req):
    logger.debug("Processing requests")
    fun = nothing
    id = 0
    msg_id = 0
    language = "en"
    if "callback_query" in req:
        try:
            language = req["callback_query"]["from"]["language_code"]
        except Exception as e:
            logger.debug("language error: {}".format(e))
            lanquage = "en"
        try:
            id = req["callback_query"]["from"]["id"]
            msg_id = req["callback_query"]["message"]["message_id"]
        except:
            return
        fun = callback_content

    if "message" in req and "text" in req["message"]:
        try:
            language = req["message"]["from"]["language_code"]
        except Exception as e:
            logger.debug(e)
            lanquage = "en"
        try:
            id = req["message"]["chat"]["id"]
            msg_id = req["message"]["message_id"]
        except:
            return
        if req["message"]["text"] == "/start":
            fun = start_content
        elif "instagram.com" in req["message"]["text"]:
            fun = instagram_link
        elif any(req["message"]["text"].startswith(x) for x in yt):
            fun = link_content
        else:
            fun = undefined_value

    return fun, id, msg_id, language


def callback_content(req, id, client, language):
    format = req["callback_query"]["data"]
    format = re.findall(r"^(\d+)\s(.+)\s(.+)\*(.+)", format)
    format = format[0]
    format_code = format[0]
    usr_link = format[1]
    typ = format[3]
    format = format[2]
    logger.debug(
        "{} choose this format: {} for this link: {}".format(id, format, usr_link)
    )
    cmd = "{} youtube-dl -o {}/{}.{} --user-agent '{}' -f '{}[filesize<50M]' '{}'".format(
        PROXY, ODIR, id, format, USER_AGENT, format_code, usr_link
    )
    dnld = asyncio.create_task(
        download_ut(client, cmd, id, format, typ, usr_link, language)
    )
    dnld.add_done_callback(partial(report_done, id))


def instagram_link(req, id, client, language):
    u = req["message"]["text"]
    if not u.startswith("http"):
        u = "https://{}".format(u)
    usr_link = urlparse(u)
    if not usr_link.netloc.endswith("instagram.com"):
        return undefined(client, id)
    cmd = "{} youtube-dl -o {}/{}.mp4 --user-agent '{}' '{}'".format(
        PROXY, ODIR, id, USER_AGENT, u
    )
    dnld = asyncio.create_task(
        download_ut(client, cmd, id, "mp4", "instagram", u, language)
    )
    dnld.add_done_callback(partial(report_done, id))


def link_content(req, id, client, language):
    u = req["message"]["text"]

    assert u.startswith("http")  # pre-condition

    up = urlparse(u)

    if up.netloc == "youtu.be":
        vid = up.path[1:]
    else:
        q = urllib.parse.parse_qs(up.query)
        if "v" not in q or not q["v"]:
            return undefined(client, id)
        vid = q["v"][0]

    if not vid:
        return undefined(client, id)

    if any(v == "'" for v in vid):
        return undefined(client, vid)

    ut_link = "https://youtu.be/{}".format(vid)
    cmd = "{} youtube-dl --dump-json '{}'".format(PROXY, ut_link)
    lst = asyncio.create_task(list_ut(client, cmd, id, ut_link, language))
    lst.add_done_callback(partial(report_done, id))


def start_content(req, id, client, language):
    strt_task = asyncio.create_task(strt(client, id, language))
    strt_task.add_done_callback(partial(report_done, id))


def undefined_value(req, id, client, language):
    unvalid = asyncio.create_task(undefined(client, id, language))
    unvalid.add_done_callback(partial(report_done, id))


async def send_warning(client, msg_id, id, language):
    logger.debug("Sending warning to {} because of too many request".format(id))

    try:
        text = TEXT["interference"][language]
        async with client.post(
            "{}/sendMessage".format(URL),
            data={"chat_id": id, "reply_to_message_id": msg_id, "text": text},
        ) as resp:
            if resp.status == 200:
                logger.debug("Warning send successfully to {}".format(id))
    except aiohttp.ClientError as ex:
        logger.debug(
            "Sending warning for too many request to id: {} failed. Exception: {}".format(
                id, ex
            )
        )


def report_done(id, fut):
    if id:
        logger.debug("Done with {}".format(id))
        busy_id.remove(id)


async def main():
    offset = -1
    async with aiohttp.ClientSession() as client:
        while True:
            user_request, offset = await fetch(client, offset)
            if not user_request:
                continue
            for req in user_request:
                fun, id, msg_id, language = req_process(req)
                language = "en" if language != "fa" else "fa"
                logger.info(req)
                if id in busy_id:
                    warning = asyncio.create_task(
                        send_warning(client, msg_id, id, language)
                    )
                    warning.add_done_callback(partial(report_done, 0))
                else:
                    busy_id.append(id)
                    fun(req, id, client, language)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.run_forever()
