load("@rules_python//python:defs.bzl", "py_library")

py_library(
    name = "text_splitter",
    srcs = [
        "text_splitter.py",
    ],
    visibility = ["//visibility:public"],
    deps = [
        "@pypi//fastapi",
        "@pypi//langchain",
    ],
)
