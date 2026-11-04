from emailqueue.controllers.RouteRegistry import routeRegistry
# Import EmailController to trigger view registration via @GetMapping / @PostMapping
import emailqueue.controllers.EmailController

urlpatterns = routeRegistry.getUrlPatterns()
