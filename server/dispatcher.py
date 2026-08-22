"""Ordered dispatch across independent HTTP route groups."""


class RouteDispatcher:
    def __init__(self, routes):
        self.routes = tuple(routes)

    def handle_get(self, handler, path, query):
        return self._dispatch("handle_get", handler, path, query)

    def handle_post(self, handler, path, query):
        return self._dispatch("handle_post", handler, path, query)

    def _dispatch(self, method_name, handler, path, query):
        for route in self.routes:
            method = getattr(route, method_name, None)
            if method is not None and method(handler, path, query):
                return True
        return False
