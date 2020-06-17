![Python application](https://github.com/digiteinfotech/rasa-dx/workflows/Python%20application/badge.svg)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/036a621f7ae74cecb3db5f01441df65e)](https://app.codacy.com/gh/digiteinfotech/rasa-dx?utm_source=github.com&utm_medium=referral&utm_content=digiteinfotech/rasa-dx&utm_campaign=Badge_Grade_Dashboard)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/digiteinfotech/rasa-dx.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/digiteinfotech/rasa-dx/alerts/)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/digiteinfotech/rasa-dx.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/digiteinfotech/rasa-dx/context:python)

# Chiron

Chiron is envisioned as a web based microservices driven suite that helps train Rasa contextual AI assistants at scale. It is designed to make the lives of those who work with ai-assistants easy, by giving them a no-coding web interface to adapt , train , test and maintain such assistants .

Adapting contextual AI assistants to specific domain is one of the bigger problems adopting chatbots within organizations. We aim to productionize cutting edge NLP solutions to help users complete the process of conveying domain knowledge to contextual assistants

At this juncture it layers on top of [Rasa Open Source] (https://rasa.com/)

# Deployment
Chiron only requires a recent version of [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).

Please do the below changes in **docker/docker-compose.yml**

1. set env variable **server** to public IP of the machine where trainer api docker container is running for example: http://localhost:8001/
    
2. set env variable **SECRET_KEY** to some random key.
    
3. use command **openssl rand -hex 32** for generating random secret key

4. run the command.
 
```shell
cd docker/
docker-compose up -d
```

5. use username: **test@demo.in** and password: **welcome@1** to try with demo user


# Development

## Installation

1. Chiron requires [python3.6](https://www.python.org/downloads/) and [mongo](https://www.mongodb.com/download-center/community)

2. Then clone this repo

```shell
git clone https://github.com/digiteinfotech/rasa-dx.git
cd rasa-dx/
```

3. For installing dependencies on windows run
```
setup.bat
```

4. For installing dependencies on linux run
```
chmod 777 setup.sh
setup.sh
```

5. For starting augment services run
```
uvicorn augment.server:app --host 0.0.0.0
```

6. For starting trainer-api services run

```
uvicorn bot_trainer.api.app.main:app --host 0.0.0.0 --port 8080
```

# Contribute

We ❤️ contributions of all size and sorts. If you find a typo, if you want to improve a section of the documentation or if you want to help with a bug or a feature, here are the steps:

1. Fork the repo and create a new branch, say rasa-dx-issue1
    
2. Fix/improve the codebase

3. write test cases and documentation for code'

4. run test cases.

```
python -m pytest
```

5. reformat code using black
```
python -m black bot_trainer
```
    
6. Commit the changes, with proper comments about the fix.
    
7. Make a pull request. It can simply be one of your commit messages.
    
8. Submit your pull request and wait for all checks passed.
    
9. Request reviews from one of the developers from our core team.
    
10. Get a 👍 and PR gets merged.


## Built With

* [Rasa](https://rasa.com/docs/) - The bot framework used
* [PiPy](https://pypi.org/) - Dependency Management
* [Mongo](https://www.mongodb.com/) - DB
* [MongoEngine](http://mongoengine.org/) - ORM
* [FastApi](https://github.com/tiangolo/fastapi) - Rest Api
* [Uvicorn](https://www.uvicorn.org/) - ASGI Server
* [Spacy](https://spacy.io/) - NLP
* [Gensim](https://radimrehurek.com/gensim/) - Embedding and Topic Modelling
* [Sentence Transformer](https://github.com/UKPLab/sentence-transformers) - Semantic Similarity
* [Pytest](https://docs.pytest.org/en/latest/) - Testing
* [MongoMock](https://github.com/mongomock/mongomock) - Mocking DB
* [Response](https://github.com/getsentry/responses) - Mocking HTTP requests
* [Black](https://github.com/psf/black) - Code Reformatting
* [NLP AUG](https://github.com/makcedward/nlpaug.git) - Augmentation


## Authors

* **Digite, Inc.** - *Initial work* - [Digite](https://digite.com)
* [Fahad Ali Shaikh](https://github.com/sfahad1414)
* [Deepak Naik](https://github.com/deenaik)
* [Nirmal Parwate](https://github.com/nirmal495)

See also the list of [contributors](https://github.com/digiteinfotech/chiron/graphs/contributors) who participated in this project.

## License
Licensed under the Apache License, Version 2.0. [Copy of the license](LICENSE.txt)
