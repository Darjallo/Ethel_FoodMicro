from langchain.text_splitter import RecursiveCharacterTextSplitter


class TextSplitter:
    chunk_size: int
    chunk_overlap: int
    """
    A class that handles text splitting using RecursiveCharacterTextSplitter.
    """

    def __init__(self, chunk_size: int = 2000, chunk_overlap: int = 400):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            add_start_index=False,  # we only need raw strings
        )

    def split_text(self, text: str) -> list[str]:
        return self.splitter.split_text(text)
