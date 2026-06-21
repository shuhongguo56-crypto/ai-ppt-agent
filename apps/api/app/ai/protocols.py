from typing import Protocol, runtime_checkable

from .models import GeneratedImage, ImageRequest, TextRequest, TextResult


@runtime_checkable
class TextGateway(Protocol):
    def generate(self, request: TextRequest) -> TextResult: ...


@runtime_checkable
class ImageGateway(Protocol):
    def generate(self, request: ImageRequest) -> GeneratedImage: ...
