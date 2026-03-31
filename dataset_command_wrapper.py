import sys
import import_declare_test

from splunklib.searchcommands import \
    dispatch, EventingCommand, Configuration, Option, validators
from ta_template_dataset_logic import transform

@Configuration()
class TatemplatedatasetCommand(EventingCommand):
    """

    ##Syntax
    tatemplatedataset field=<fieldname>

    ##Description
    Template dataset processing command — operates on the full result set.

    """

    field = Option(name='field', require=True, validate=validators.Fieldname())

    def transform(self, events):
       return transform(self, events)

dispatch(TatemplatedatasetCommand, sys.argv, sys.stdin, sys.stdout, __name__)