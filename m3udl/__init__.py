from .main import Preprocess
from .download import Download
from . import configure

from .__version__ import __author__, __author_email__, __version__, __title__
from .__version__ import __copyright__, __description__

UA = configure.UA
__all__ = ('Preprocess', 'Download', 'UA')


def setting(verify=True, timeout=30):
    configure.VERIFY = bool(verify)
    configure.TIMEOUT = timeout
    # disable warnings
    if not verify:
        import urllib3
        urllib3.disable_warnings()
