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


def match_element(el: AupData | str, filter_dict: dict, by_attr: str | None = None):
    accept = True
    decline = True

    for attr in el.__dict__:
        if attr in filter_dict['accept']:
            accept = accept and any(
                [str(condition).lower() in str(el.__getattribute__(attr)).lower() for condition in
                 filter_dict['accept'][attr]])

        if attr in filter_dict['decline']:
            decline = decline and all(
                str(condition).lower() not in str(el.__getattribute__(attr)).lower() for condition in
                filter_dict['decline'][attr])

    return accept and decline

def match_attribute(el: str, attr: str, filter_dict: dict):
    accept = True
    decline = True

    if attr in filter_dict['accept']:
        accept = accept and any(
            [str(condition).lower() in str(el).lower() for condition in
             filter_dict['accept'][attr]])

    if attr in filter_dict['decline']:
        decline = decline and all(
            str(condition).lower() not in str(el).lower() for condition in
            filter_dict['decline'][attr])

    return accept and decline