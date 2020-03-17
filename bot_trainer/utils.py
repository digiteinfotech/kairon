import yaml

class Utility:

    @staticmethod
    def load_yaml(file, mode="r"):
        data = None
        with open(file, mode=mode) as fp:
           data = yaml.load(fp, loader= yaml.FullLoader)
        return data