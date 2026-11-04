import pytest
from django.test import RequestFactory
from django.views import View
from django.http import HttpResponse

from emailqueue.controllers.RouteRegistry import (
    RouteRegistry,
    RouteDefinition,
    GetMapping,
    PostMapping,
    RequestMapping,
    HTTP_GET,
    HTTP_POST,
)

class TestRouteRegistry:
    def setup_method(self):
        self.factory = RequestFactory()

    def testConvertPathToRegex(self):
        assert RouteDefinition._convertPathToRegex("") == r"^/?$"
        assert RouteDefinition._convertPathToRegex("counts") == r"^counts/?$"
        assert RouteDefinition._convertPathToRegex("users/{userId}/emails/{emailId}") == r"^users/(?P<userId>[a-zA-Z0-9_\-]+)/emails/(?P<emailId>[a-zA-Z0-9_\-]+)/?$"

    def testPostMappingDecoratorRegistersRoute(self):
        testRegistry = RouteRegistry()
        
        # Test custom class decoration
        @PostMapping(path="test-post", name="testPostRoute")
        class SamplePostView(View):
            def post(self, request):
                return HttpResponse("posted", status=201)

        # Check that the global registry registered it
        patterns = [r.name for r in testRegistry.getInstance().routes]
        assert "testPostRoute" in patterns

    def testMethodEnforcementReturns405(self):
        @GetMapping(path="only-get", name="onlyGetRoute")
        class OnlyGetView(View):
            def get(self, request):
                return HttpResponse("ok", status=200)

        urlPattern = None
        for route in RouteRegistry.getInstance().routes:
            if route.name == "onlyGetRoute":
                urlPattern = route.toUrlPattern()
                break

        assert urlPattern is not None

        # Call with POST: should receive 405 Method Not Allowed
        postRequest = self.factory.post("/only-get")
        response = urlPattern.callback(postRequest)
        assert response.status_code == 405

        # Call with GET: should succeed with 200 OK
        getRequest = self.factory.get("/only-get")
        response = urlPattern.callback(getRequest)
        assert response.status_code == 200

