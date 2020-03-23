from distutils.core import setup
from Cython.Build import cythonize

setup(
    ext_modules = cythonize("bot_trainer/**.py",language_level = "3")
)