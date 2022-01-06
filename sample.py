import os
from rasa.shared.constants import DEFAULT_MODELS_PATH
from glob import glob

output = os.path.join(DEFAULT_MODELS_PATH, "tests")
new_model = "models/tests/20211116-144823.tar.gz"
if os.path.isdir(output):
    new_path = os.path.join(output, "old_model")
    if not os.path.exists(new_path):
        os.mkdir(new_path)
    for cleanUp in glob(os.path.join(output, '*.tar.gz')):
        print(cleanUp)


from smtplib import SMTP
import re

re.findall(r"{[a-zA-Z0-9]*}", "Hello {How} are {you}")
