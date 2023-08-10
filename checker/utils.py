from timeit import default_timer as timer


def method_time(method):
    def wrapper(cls, *args, **kwargs):
        start = timer()
        result = method(cls, *args, **kwargs)
        print(
            f"[Timer] Method <{type(cls).__name__}.{method.__name__}> executed in {round((timer() - start) * 1000, 2)} ms.")
        return result

    return wrapper


def match_disciple(discipline: str, filter_conditions: dict):
    return (any([condition in discipline.lower() for condition in filter_conditions['accept']]) and
            all([condition not in discipline.lower() for condition in filter_conditions['decline']]))
