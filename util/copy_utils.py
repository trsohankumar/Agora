def append_to_list(og_list, item):
    if item in og_list:
        return
    temp_list = og_list
    temp_list.append(item)
    return temp_list


def add_item_to_dict(og_dict, key, item_key, item_value):
    if key not in og_dict:
        return
    value = og_dict[key]
    value[item_key] = item_value
    og_dict.update({key: value})


def copy_dicts(source, destination):
    for key, value in source.items():
        destination[key] = value


def safe_copy(source, destination, manager):
    for key, value in source.items():
        if key not in destination:
            destination[key] = manager.dict()
            destination[key].append(value)
