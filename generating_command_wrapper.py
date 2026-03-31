import sys
import import_declare_test

from splunklib.searchcommands import \
    dispatch, GeneratingCommand, Configuration, Option, validators
from ta_template_generating_logic import generate

@Configuration()
class TatemplategeneratingCommand(GeneratingCommand):
    """

    ##Syntax
    | tatemplategenerating count=<integer>

    ##Description
    Template generating command — produces records from scratch.

    """
    count = Option(name='count', require=True, validate=validators.Integer(minimum=1))

    def generate(self):
       return generate(self)

dispatch(TatemplategeneratingCommand, sys.argv, sys.stdin, sys.stdout, __name__)