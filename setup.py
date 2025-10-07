#!/usr/bin/env python
"""Async-Notify Setup."""

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext
from Cython.Build import cythonize

COMPILE_ARGS = ["-O2"]

extensions = [
    Extension(
        name="notify.exceptions",
        sources=["notify/exceptions.pyx"],
        extra_compile_args=COMPILE_ARGS,
        language="c",
    ),
    Extension(
        name="notify.types.typedefs",
        sources=["notify/types/typedefs.pyx"],
        extra_compile_args=COMPILE_ARGS,
        # language defaults to C; set language="c++" if needed
    ),
]

class BuildExtensions(build_ext):
    """Ensure cythonization during build."""
    def build_extensions(self):
        try:
            self.extensions = cythonize(self.extensions)
        except ImportError:
            print("Cython not found. Building without cythonization.")
        super().build_extensions()

if __name__ == "__main__":
    setup(
        ext_modules=cythonize(extensions),
        cmdclass={"build_ext": BuildExtensions},
    )
