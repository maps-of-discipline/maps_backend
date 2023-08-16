from timeit import default_timer as timer

from models import AupData


def method_time(method):
    def wrapper(cls, *args, **kwargs):
        start = timer()
        result = method(cls, *args, **kwargs)
        print(
            f"[Timer] Method <{type(cls).__name__}.{method.__name__}> executed in {round((timer() - start) * 1000, 2)} ms.")
        return result

    return wrapper


def match_element(el: AupData, filter_dict: dict):
    accept = True
    decline = True

    for attr in el.__dict__:
        if attr in filter_dict['accept']:
            accept = accept and any(
                [condition in el.__getattribute__(attr) for condition in filter_dict['accept'][attr]])

        if attr in filter_dict['decline']:
            decline = decline and all(
                condition not in el.__getattribute__(attr) for condition in filter_dict['decline'][attr])

    return accept and decline
