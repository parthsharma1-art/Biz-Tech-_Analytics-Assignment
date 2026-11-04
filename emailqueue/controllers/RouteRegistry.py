import re
from typing import List, Optional, Callable, Type, Union
from django.urls import re_path
from django.views import View
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed

HTTP_GET = "GET"
HTTP_POST = "POST"
HTTP_PUT = "PUT"
HTTP_DELETE = "DELETE"

class RouteDefinition:
    def __init__(
        self,
        path: str,
        viewCallable: Callable,
        methods: Optional[List[str]] = None,
        name: Optional[str] = None,
    ):
        self.path = path
        self.viewCallable = viewCallable
        self.methods = [m.upper() for m in methods] if methods else None
        self.name = name

    def toUrlPattern(self):
        regexPattern = self._convertPathToRegex(self.path)
        viewHandler = self._wrapWithMethodCheck(self.viewCallable, self.methods)
        return re_path(regexPattern, viewHandler, name=self.name)

    @staticmethod
    def _convertPathToRegex(pathStr: str) -> str:
        cleanedPath = pathStr.strip("/")
        if not cleanedPath:
            return r"^/?$"
        # Convert Spring Boot style placeholder {paramName} to Django regex (?P<paramName>[a-zA-Z0-9_\-]+)
        converted = re.sub(r"\{([a-zA-Z0-9_]+)\}", r"(?P<\1>[a-zA-Z0-9_\-]+)", cleanedPath)
        return rf"^{converted}/?$"

    @staticmethod
    def _wrapWithMethodCheck(viewHandler: Callable, allowedMethods: Optional[List[str]]) -> Callable:
        if not allowedMethods:
            return viewHandler

        def methodEnforcingView(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if request.method not in allowedMethods:
                return HttpResponseNotAllowed(allowedMethods)
            return viewHandler(request, *args, **kwargs)

        # Preserve view name and metadata for Django
        methodEnforcingView.__name__ = getattr(viewHandler, "__name__", "wrappedView")
        methodEnforcingView.__doc__ = getattr(viewHandler, "__doc__", None)
        return methodEnforcingView


class RouteRegistry:
    _instance: Optional["RouteRegistry"] = None

    def __init__(self):
        self.routes: List[RouteDefinition] = []

    @classmethod
    def getInstance(cls) -> "RouteRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def registerRoute(
        self,
        target: Union[Type[View], Callable],
        path: str = "",
        methods: Optional[List[str]] = None,
        name: Optional[str] = None,
    ) -> None:
        if isinstance(target, type) and issubclass(target, View):
            viewCallable = target.as_view()
        else:
            viewCallable = target

        routeDef = RouteDefinition(
            path=path,
            viewCallable=viewCallable,
            methods=methods,
            name=name or getattr(target, "__name__", None),
        )
        self.routes.append(routeDef)

    def getUrlPatterns(self) -> list:
        return [route.toUrlPattern() for route in self.routes]

    def clearRoutes(self) -> None:
        self.routes.clear()


# Global Singleton Registry
routeRegistry = RouteRegistry.getInstance()


# Spring Boot-inspired decorators
def RequestMapping(path: str = "", methods: Optional[List[str]] = None, name: Optional[str] = None):
    """Spring Boot @RequestMapping equivalent for Django views."""
    def decorator(targetClassOrFunc):
        routeRegistry.registerRoute(
            target=targetClassOrFunc,
            path=path,
            methods=methods,
            name=name or getattr(targetClassOrFunc, "__name__", None),
        )
        return targetClassOrFunc
    return decorator


def GetMapping(path: str = "", name: Optional[str] = None):
    """Spring Boot @GetMapping equivalent for Django views."""
    return RequestMapping(path=path, methods=[HTTP_GET], name=name)


def PostMapping(path: str = "", name: Optional[str] = None):
    """Spring Boot @PostMapping equivalent for Django views."""
    return RequestMapping(path=path, methods=[HTTP_POST], name=name)


def PutMapping(path: str = "", name: Optional[str] = None):
    """Spring Boot @PutMapping equivalent for Django views."""
    return RequestMapping(path=path, methods=[HTTP_PUT], name=name)


def DeleteMapping(path: str = "", name: Optional[str] = None):
    """Spring Boot @DeleteMapping equivalent for Django views."""
    return RequestMapping(path=path, methods=[HTTP_DELETE], name=name)

