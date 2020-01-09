import time
import re
import m3udl

m3udl.setting(True, 15)


def handel_url():
    url = input('请输入url:').strip()
    # if not re.match(r'https?:/{2}\w.+\.m3u8?.+$', url, re.IGNORECASE):
    if not re.match(r'https?:/{2}\w.+$', url):
        print('\n\n# -----------------------------')
        input('# 请输入合法的url，按下回车键退出。')
        exit(0)

    print('\nurl 解析中……')
    retries = 10
    _pre = m3udl.Preprocess(url)
    _playlist, _duration = _pre.get_target_url()
    while _duration == 0 and retries > 0:
        _playlist, _duration = _pre.get_target_url()
        retries -= 1

    if _duration == 0 and retries == 0:
        print('\n\n# -----------------------------------------------')
        input('# 重试次数达到上限！url 解析失败！请按下回车键退出。')
        exit(0)
    if _duration == -1 or not _playlist:
        print('\n\n# ------------------------------------------')
        input('# 该url定位的资源不是可用的m3u8文件，请按下回车键退出。')
        exit(0)

    return _pre.default_name, _playlist, m3udl.Preprocess.init_duration(_duration)


def handle_input(_default_name):
    _thread_num = 0
    while True:
        try:
            if _thread_num > 32 or not _thread_num:
                _thread_num = int(input('请输入线程数目:'))
            if 0 < _thread_num <= 32:
                _path = input('请输入存储路径:')
                break
            print('线程数不能为0，建议线程数小于32，', end='')
        except ValueError:
            pass
        except EOFError:
            print()
    if _path and not re.search(r'[/\\]', _path):
        _path = './' + _path
    res = re.search(r'(.*[/\\])(.+\.\w+)$', _path)
    _filename = res.group(2) if res else _default_name
    _path = res.group(1) if res else _path

    return _filename, _path, _thread_num


default_name, playlist, video_duration = handel_url()
filename, path, thread_num = handle_input(default_name)

start_time = time.time()
downloader = m3udl.download.Download(filename, playlist, path, thread_num, max_retries=10)
downloader.start(video_duration)
end_time = time.time()

input('\n\n下载完毕，用时: %s，请按下回车键退出。' % m3udl.Preprocess.init_duration(end_time - start_time))
