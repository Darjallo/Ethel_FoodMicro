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
    name = "flow_manager",
    srcs = ["__main__.py"],
    main = "__main__.py",
    deps = [
        "//ethel/flow_manager:models",
        "@pypi//fastapi",
        "@pypi//uvicorn",
    ],
)

# TODO build OCI image
