![Python application](https://github.com/digiteinfotech/rasa-dx/workflows/Python%20application/badge.svg)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/8b029ffa2fc547febb6899d4ba880083)](https://www.codacy.com/gh/digiteinfotech/kairon/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=digiteinfotech/kairon&amp;utm_campaign=Badge_Grade)
[![Coverage Status](https://coveralls.io/repos/github/digiteinfotech/kairon/badge.svg)](https://coveralls.io/github/digiteinfotech/kairon)




Kairon is now envisioned as a conversational digital transformation platform that helps build LLM based digital assistants at scale. It is designed to make the lives of those who work with ai-assistants easy, by giving them a no-coding web interface to adapt , train , test and maintain such assistants . We are now enhancing the backbone of Kairon with a full fledged context management system to build proactive digital assistants . 

**What is Kairon?**

Kairon is currently a set of tools  built on the RASA framework with a helpful UI interface .
While RASA focuses on technology of chatbots itself. Kairon on the other hand focuses on technology that deal with pre-processing of data that are needed by this framework. These include question augmentation and generation of knowledge graphs that can be used to automatically generate intents, questions and responses.
It also deals with the post processing and maintenance of these bots such metrics / follow-up messages etc. 

**What can it do?**

Kairon is open-source. It is a Conversational digital transformation platform: Kairon is a platform that allows companies to create and deploy digital assistants to interact with customers in a conversational manner.

**End-to-end lifecycle management**: Kairon takes care of the entire digital assistant lifecycle, from creation to deployment and monitoring, freeing up company resources to focus on other tasks.
Tethered digital assistants: Kairon’s digital assistants are tethered to the platform, which allows for real-time monitoring of their performance and easy maintenance and updates as needed.

**Low-code/no-code interface:** Kairon’s interface is designed to be easy for functional users, such as marketing teams or product management, to define how the digital assistant responds to user queries without needing extensive coding skills.
Secure script injection: Kairon’s digital assistants can be easily deployed on websites and SAAS products through secure script injection, enabling organizations to offer better customer service and support.

**Kairon Telemetry:** Kairon’s telemetry feature monitors how users are interacting with the website/product where Kairon was injected and proactively intervenes if they are facing problems, improving the overall user experience.
Chat client designer: Kairon’s chat client designer feature allows organizations to create customized chat clients for their digital assistants, which can enhance the user experience and help build brand loyalty.

**Analytics module:** Kairon’s analytics module provides insights into how users are interacting with the digital assistant, enabling organizations to optimize their performance and provide better service to customers.
Robust integration suite: Kairon’s integration suite allows digital assistants to be served in an omni-channel, multi-lingual manner, improving accessibility and expanding the reach of the digital assistant.

**Realtime struggle analytics:** Kairon’s digital assistants use real-time struggle analytics to proactively intervene when users are facing friction on the product/website where Kairon has been injected, improving user satisfaction and reducing churn.
This website can be found at [Kairon](https://kairon.nimblework.com/) and is hosted by NimbleWork Inc. 

**Who uses it ?**

Kairon is built for two personas 
Teams and Individuals who want an easy no-coding interface to create, train, test and deploy digital assistants . One can directly access these features from our hosted website. Teams who want to host the chatbot trainer in-house. They can build it using docker compose. 
Our teams current focus within NLP is Knowledge Graphs – Do let us know if you are interested. 


At this juncture it layers on top of [Rasa Open Source](https://rasa.com/)

# Deployment
Kairon only requires a recent version of [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).

Build the application image from the repository root:

```shell
docker build -f docker/Dockerfile -t kairon .
```

The image installs Python 3.10 and the locked dependencies with [uv](https://docs.astral.sh/uv/). PyTorch and TensorFlow are the CPU builds. `docker/docker-compose.yml` runs the API, chat, action, history, events, worker, and script services from this `kairon` image.

Please do the below changes in **docker/docker-compose.yml**

1. set env variable **server** to public IP of the machine where trainer api docker container is running for example: http://localhost:81

2. **Optional**, if you want to have google analytics enabled then uncomment **trackingid**
and set google analytics tracking id
    
3. set env variable **SECRET_KEY** to some random key.

   use below command for generating random secret key 
   ```shell
   openssl rand -hex 32
   ```
4. run the command.
 
   ```shell
   cd kairon/docker
   docker-compose up -d
   ```

5. Open http://localhost/ in browser.

6. To Test use username: **test@demo.in** and password: **Changeit@123** to try with demo user


# Development

## Installation

1. Kairon requires Python 3.10 and [mongo 4.0+](https://www.mongodb.com/download-center/community). On Linux, [uv](https://docs.astral.sh/uv/) installs that Python.

2. Then clone this repo

   ```shell
   git clone https://github.com/digiteinfotech/kairon.git
   cd kairon/
   ```

3. For installing dependencies

   **Linux**
   ```
   chmod +x ./setup.sh
   ./setup.sh
   ```

   `setup.sh` installs uv if it is missing and syncs `.venv` from `uv.lock`. Rasa is the standard package, without the spaCy extra or NLTK. Run the app with `uv run`, for example `uv run python -m uvicorn kairon.api.app.main:app --host 0.0.0.0 --port 8080`.

   **Windows**
   ```
   setup.bat
   ```

   `setup.bat` installs uv if it is missing and syncs `.venv` from `uv.lock`. The lock is solved for Linux. Rasa pins `numpy==1.22.3` on Windows, which conflicts with `pandas==2.2.2`, so `uv sync` does not install on Windows. tensorflow-text also has no Windows build.

4. For starting trainer-api services run

   ```
   uv run python -m uvicorn kairon.api.app.main:app --host 0.0.0.0 --port 8080
   ```
   
## System Configuration

### Email verification setup
The email.yaml file can be used to configure the process for account confirmation through a verification link sent to the user's mail id. It consists of the following parameters:

* **enable** -
 
   set value to True for enabling email verification, and False to disable.
   
   You can also use the environment variable **EMAIL_ENABLE** to change the values.
* **url** - 

  this url, along with a unique token is sent to the user's mail id for account verification as well as for password reset tasks.
   
  You can also use the environment variable **APP_URL** to change the values.
* **email** - 

  the mail id of the account which sends the confirmation mail.
   
  You can also use the environment variable **EMAIL_SENDER_EMAIL** to change the values.
* **password** -
 
  the password of the account which sends the confirmation mail.
 
  You can also use the environment variable **EMAIL_SENDER_PASSWORD** to change the values.
* **port** - 

  the port that is used to send the mail [For ex. "587"].

  You can also use the environment variable **EMAIL_SENDER_PORT** to change the values.
* **service** - 

  the mail service that is used to send the confirmation mail [For ex. "gmail"].
 
  You can also use the environment variable **EMAIL_SENDER_SERVICE** to change the values.
* **tls** -
 
   set value to True for enabling transport layer security, and False to disable.
   
   You can also use the environment variable **EMAIL_SENDER_TLS** to change the values.
* **userid** - 

  the user ID for the mail service if you're using a custom service for sending mails.
   
  You can also use the environment variable **EMAIL_SENDER_USERID** to change the values.
* **confirmation_subject** -

  the subject of the mail to be sent for confirmation.
  
  You can also use the environment variable **EMAIL_TEMPLATES_CONFIRMATION_SUBJECT** to change the subject.
* **confirmation_body** -

  the body of the mail to be sent for confirmation.
  
  You can also use the environment variable **EMAIL_TEMPLATES_CONFIRMATION_BODY** to change the body of the mail.
* **confirmed_subject** -

  the subject of the mail to be sent after confirmation.
  
  You can also use the environment variable **EMAIL_TEMPLATES_CONFIRMED_SUBJECT** to change the subject.
* **confirmed_body** -

  the body of the mail to be sent after confirmation.
  
  You can also use the environment variable **EMAIL_TEMPLATES_CONFIRMED_BODY** to change the body of the mail.
* **password_reset_subject** -

  the subject of the mail to be sent for password reset.
  
  You can also use the environment variable **EMAIL_TEMPLATES_PASSWORD_RESET_SUBJECT** to change the subject.
* **password_reset_body** -

  the body of the mail to be sent for password reset.
  
  You can also use the environment variable **EMAIL_TEMPLATES_PASSWORD_RESET_BODY** to change the body of the mail.
* **password_changed_subject** -

  the subject of the mail to be sent after changing the password.
  
  You can also use the environment variable **EMAIL_TEMPLATES_PASSWORD_CHANGED_SUBJECT** to change the subject.
* **password_changed_body** -

  the body of the mail to be sent after changing the password.
  
  You can also use the environment variable **EMAIL_TEMPLATES_PASSWORD_CHANGED_BODY** to change the body of the mail.  

# Documentation

Documentation for all APIs for Kairon are still being fleshed out. A intermediary version of the documentation is available here.
[Documentation](http://kairon-docs.digite.com/)




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
* [Pytest](https://docs.pytest.org/en/latest/) - Testing
* [MongoMock](https://github.com/mongomock/mongomock) - Mocking DB
* [Response](https://github.com/getsentry/responses) - Mocking HTTP requests
* [Black](https://github.com/psf/black) - Code Reformatting
* [NLP AUG](https://github.com/makcedward/nlpaug.git) - Augmentation


## Authors
The repository is being maintained and supported by **NimbleWork Inc.**
* **NimbleWork.Inc** - [NimbleWork](https://www.nimblework.com/)
* [Fahad Ali Shaikh](https://github.com/sfahad1414)
* [Deepak Naik](https://github.com/deenaik)
* [Nirmal Parwate](https://github.com/nirmal495)
* [Adurthi Ashwin Swarup](https://github.com/Leothorn)
* [Udit Pandey](https://github.com/udit-pandey)
* [Nupur_Khare](https://github.com/nupur-khare)
* [Rohan Patwardhan]
* [Hitesh Ghuge]
* [Sushant Patade]
* [Mitesh Gupta]

See also the list of [contributors](https://github.com/digiteinfotech/kairon/graphs/contributors) who participated in this project.

## License
Licensed under the Apache License, Version 2.0. [Copy of the license](LICENSE.txt)

A list of the Licenses of the dependencies of the project can be found at the [Link](https://www.digite.com/kairon/libraries/)
