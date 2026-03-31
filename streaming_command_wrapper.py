import sys
import import_declare_test

from splunklib.searchcommands import \
    dispatch, StreamingCommand, Configuration, Option, validators
from ta_template_streaming_logic import stream

@Configuration()
class TatemplatestreamingCommand(StreamingCommand):
    """

    ##Syntax
    tatemplatestreaming field=<fieldname>

    ##Description
    Template streaming command — processes records one at a time.

    """

    field = Option(name='field', require=True, validate=validators.Fieldname())

    def stream(self, events):
        return stream(self, events)

dispatch(TatemplatestreamingCommand, sys.argv, sys.stdin, sys.stdout, __name__)