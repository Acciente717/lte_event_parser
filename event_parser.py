### Copyright [2019] Zhiyao Ma
import sys
import inspect

from parsers.ParserBase import ParserBase
from parsers.HandoverSuccessParser import HandoverSuccessParser
from parsers.HandoverFailureParser import HandoverFailureParser
from parsers.FastRecoverAfterRLFParser import FastRecoverAfterRLFParser
from parsers.SlowRecoverAfterRLFParser import SlowRecoverAfterRLF

def extract_info(line):
    timestamp, pkt_type, fields = (i.strip() for i in line.split("$"))
    fields = { i.split(':')[0].strip() : ':'.join(i.split(':')[1:]).strip()
               for i in fields.split(',')
               if i.strip() != '' }
    return timestamp, pkt_type, fields

def run():
    shared_states = {
        'last_serving_cell_dl_freq' : None,
        'last_serving_cell_ul_freq' : None,
        'last_serving_cell_id' : None,
        'last_serving_cell_identity' : 'Unknown',
        'reset_all' : False,
        'stall_once' : False
    }
    active_parsers = [
        i(shared_states) for i in globals().values()
        if inspect.isclass(i)
        and issubclass(i, ParserBase)
        and i is not ParserBase
    ]

    line_num = 0
    while True:
        try:
            if not shared_states['stall_once']:
                line = input()
                line_num += 1
            else:
                shared_states['stall_once'] = False

            if shared_states['reset_all']:
                for active_parser in active_parsers:
                    active_parser.reset()
                shared_states['reset_all'] = False
            for active_parser in active_parsers:
                active_parser.run(extract_info(line))
        except EOFError:
            break
        except Exception as e:
            print('Exception at line', line_num)
            print(e)
            sys.exit(1)

if __name__ == '__main__':
    run()
