# run the __main__.py file in this directory

load("@rules_python//python:defs.bzl", "py_binary")

py_binary(
    name = "chunking_service",
    srcs = ["__main__.py"],
    main = "__main__.py",
    deps = [
        "//pyethel/chunking:text_splitter",
        "@pypi//fastapi",
        "@pypi//pydantic",
        "@pypi//uvicorn",
    ],
)

# TODO build OCI image
