# encoding = utf-8
# Always put this line at the beginning of this file
import import_declare_test

import os
import sys

from splunktaucclib.alert_actions_base import ModularAlertBase
import ta_template_alert_helper

class AlertActionWorkerta_template_alert(ModularAlertBase):

    def __init__(self, ta_name, alert_name):
        super(AlertActionWorkerta_template_alert, self).__init__(ta_name, alert_name)

    def validate_params(self):


        if not self.get_param("webhook_url"):
            self.log_error('webhook_url is a mandatory parameter, but its value is None.')
            return False

        if not self.get_param("severity"):
            self.log_error('severity is a mandatory parameter, but its value is None.')
            return False
        return True

    def process_event(self, *args, **kwargs):
        status = 0
        try:
            if not self.validate_params():
                return 3
            status = ta_template_alert_helper.process_event(self, *args, **kwargs)
        except Exception as e:
            msg = "Unexpected error: {}."
            if str(e):
                self.log_error(msg.format(str(e)))
            else:
                import traceback
                self.log_error(msg.format(traceback.format_exc()))
            return 5
        return status

if __name__ == "__main__":
    exitcode = AlertActionWorkerta_template_alert("ta_sad_ucc_package_template", "ta_template_alert").run(sys.argv)
    sys.exit(exitcode)
