# run the __main__.py file in this directory

load("@rules_python//python:defs.bzl", "py_binary", "py_library")

py_library(
    name = "models",
    srcs = ["models.py"],
    deps = [
        "@pypi//pydantic",
    ],
)

py_binary(
    name = "chunking_service",
    srcs = ["__main__.py"],
    main = "__main__.py",
    deps = [
        "//ethel/chunking_service:models",
        "//pyethel/chunking:text_splitter",
        "@pypi//fastapi",
        "@pypi//uvicorn",
    ],
)

# TODO build OCI image
