def serialize(models):
    if isinstance(models, list):
        return [r.to_dict() for r in models]
    else:
        return models.to_dict()