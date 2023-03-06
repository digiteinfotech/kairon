import requests

class WABAClient(object):
    MESSAGING_TYPES = {
        'text',
        'image',
        'location',
        'contacts',
        'interactive',
        'template'
    }

    def __init__(self, waba_conf, from_phone_number_id, **kwargs):
        self.from_phone_number_id = from_phone_number_id
        self.api_key = waba_conf.get("api_key")
        self.session = kwargs.get('session', requests.Session())
        self.base_url_waba = 'https://waba.360dialog.io/v1'

    @property
    def auth_headers(self):
        auth = {
            'D360-API-KEY': self.api_key
        }
        return auth

    def send(self, payload, to_phone_number, messaging_type, recipient_type='individual', timeout=None, tag=None):
        """
            @required:
                payload: message request payload
                to_phone_number: receiver's phone number
                messaging_type: text/document, etc
            @optional:
                recipient_type: recipient type
                timeout: request timeout
                tag
            @outputs: response json
        """
        if messaging_type not in self.MESSAGING_TYPES:
            raise ValueError('`{}` is not a valid `messaging_type`'.format(messaging_type))

        body = {
            'recipient_type': recipient_type,
            "to": to_phone_number,
            "type": messaging_type,
            messaging_type: payload
        }

        if tag:
            body['tag'] = tag

        return self.send_action(body)

    def send_json(self, payload: dict, to_phone_number, recipient_type='individual', timeout=None):
        """
            @required:
                payload: message request payload
                to_phone_number: receiver's phone number
            @optional:
                recipient_type: recipient type
                timeout: request timeout
            @outputs: response json
        """
        payload.update({
            'recipient_type': recipient_type,
            "to": to_phone_number
        })

        return self.send_action(payload)

    def send_template(self, template, to_phone_number, messaging_type="template", timeout=None, tag=None, **kwargs):
        body = {
            "to": to_phone_number,
            "type": messaging_type,
            messaging_type: template
        }

        if tag:
            body['tag'] = tag

        return self.send_action(body)

    def send_action(self, payload, timeout=None, **kwargs):
        """
            @required:
                payload: message request payload
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.post('{base_url_waba}/messages'.format(base_url_waba=self.base_url_waba),
            headers=self.auth_headers,
            json=payload,
            timeout=timeout
        )
        return r.json()

    def get_attachment(self, media_id, timeout=None):
        """
            @required:
                media_id: audio/video/image/document id
            @optional:
                timeout: request timeout
            @outputs: response json
        """
        r = self.session.get(
            '{base_url_waba}/media/{media_id}'.format(
                base_url_waba=self.base_url_waba, media_id=media_id
            ),
            headers=self.auth_headers,
            timeout=timeout
        )
        return r.json()

    def get_template(self, template_id):
        return

    def mark_as_read(self, msg_id, timeout=None):
        r = self.session.put('{base_url_waba}/messages/{msg_id}'.format(base_url_waba=self.base_url_waba, msg_id=msg_id),
            headers=self.auth_headers,
            json={"status": True},
            timeout=timeout
        )
        return r.json()
