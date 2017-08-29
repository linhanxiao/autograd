import warnings
from contextlib import contextmanager
from .util import subvals, wraps

def trace(start_nodes, fun, x):
    with trace_stack.new_trace() as trace:
        start_boxes = box(x, start_nodes, trace)
        end_boxes = fun(start_boxes)
        return unbox(end_boxes, trace)

def box(xs, nodes, trace):
    return umap(lambda x, node: new_box(x, trace, node), xs, nodes)

def unbox(xs, trace):
    def unbox_noncontainer(x):
        if isbox(x) and x._trace == trace:
            return NotATuple((x._value, x._node))
        else:
            warnings.warn("Output seems independent of input.")
            return NotATuple((x, None))

    return uunzip(umap(unbox_noncontainer, xs))

class NotATuple(tuple): pass

def umap(f, *args):
    xs = args[0]
    t = type(xs)
    if t is tuple:
        return tuple([umap(f, *args) for args in zip(*args)])
    else:
        return f(*args)

def uunzip(xs):
    t = type(xs)
    if t is tuple:
        return tuple(zip(*map(uunzip, xs)))
    else:
        return xs

def uflatten(xs):
    L = []
    umap(L.append, xs)
    return L

class Node(object):
    __slots__ = []
    def __init__(self, value, fun, args, kwargs, parent_argnums, parents):
        assert False

    def initialize_root(self, *args, **kwargs):
        assert False

    @classmethod
    def new_root(cls, *args, **kwargs):
        root = cls.__new__(cls)
        root.initialize_root(*args, **kwargs)
        return root

def primitive(f_raw):
    """
    Wraps a function so that its gradient can be specified and its invocation
    can be recorded. For examples, see the docs."""
    @wraps(f_raw)
    def f_wrapped(*args, **kwargs):
        boxed_args, trace, node_constructor = find_top_boxed_args(args)
        if boxed_args:
            argvals = subvals(args, [(argnum, box._value) for argnum, box in boxed_args])
            parents = [box._node for _     , box in boxed_args]
            argnums = [argnum    for argnum, _   in boxed_args]
            ans = f_wrapped(*argvals, **kwargs)
            node = node_constructor(ans, f_wrapped, argvals, kwargs, argnums, parents)
            return new_box(ans, trace, node)
        else:
            return f_raw(*args, **kwargs)
    return f_wrapped

def notrace_primitive(f_raw):
    @wraps(f_raw)
    def f_wrapped(*args, **kwargs):
        argvals = map(getval, args)
        return f_raw(*argvals, **kwargs)
    f_wrapped._is_primitive = True
    return f_wrapped

def find_top_boxed_args(args):
    top_trace = -1
    top_boxes = []
    top_node_type = None
    for argnum, arg in enumerate(args):
        if isbox(arg):
            trace = arg._trace
            if trace > top_trace:
                top_boxes = [(argnum, arg)]
                top_trace = trace
                top_node_type = type(arg._node)
            elif trace == top_trace:
                top_boxes.append((argnum, arg))
    return top_boxes, top_trace, top_node_type

class TraceStack(object):
    def __init__(self):
        self.top = -1
    @contextmanager
    def new_trace(self):
        self.top += 1
        yield self.top
        self.top -= 1
trace_stack = TraceStack()

class Box(object):
    __slots__ = ['_value', '_trace', '_node']
    def __init__(self, value, trace, node):
        self._value = value
        self._node = node
        self._trace = trace

    def __bool__(self):
        return bool(self._value)

    __nonzero__ = __bool__

    def __str__(self):
        return "Autograd {0} with value {1}".format(
            type(self).__name__, str(self._value))

def toposort(end_nodes):
    child_counts = {}
    stack = list(end_nodes)
    while stack:
        node = stack.pop()
        if node in child_counts:
            child_counts[node] += 1
        else:
            child_counts[node] = 1
            stack.extend(node.parents)

    childless_nodes = list(end_nodes)
    while childless_nodes:
        node = childless_nodes.pop()
        yield node
        for parent in node.parents:
            if child_counts[parent] == 1:
                childless_nodes.append(parent)
            else:
                child_counts[parent] -= 1

box_type_mappings = {}
box_types = set()
def register_box(box_type, value_type):
    box_types.add(box_type)
    box_type_mappings[value_type] = box_type
    box_type_mappings[box_type] = box_type

def new_box(value, trace, node):
    try:
        return box_type_mappings[type(value)](value, trace, node)
    except KeyError:
        raise TypeError("Can't differentiate w.r.t. type {}".format(type(value)))

isbox  = lambda x: type(x) in box_types  # almost 3X faster than isinstance(x, Box)
getval = lambda x: getval(x._value) if isbox(x) else x
