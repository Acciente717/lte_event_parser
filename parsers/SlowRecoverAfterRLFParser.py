### Copyright [2019] Zhiyao Ma
from .ParserBase import ParserBase
class SlowRecoverAfterRLF(ParserBase):
    def __init__(self, shared_states):
        super().__init__(shared_states)
        self.reset_to_normal_state()
        self.have_sent_meas_report_to_current_cell = False
        self.trying_cell_dl_freq = None
        self.trying_cell_ul_freq = None
        self.trying_cell_id = None
        self.trying_cell_identity = None
        self.last_packet_timestamp_before_rlf = None
        self.just_switched = False

    def reset_to_normal_state(self):
        self.reestablishment_requested_on_rlf = False
        self.mac_rach_triggered_by_rlf = False
        self.mac_rach_attempt_succeeded = False
        self.connection_setup = False
        self.rrc_reconfiguration_started = False
        self.reestablishment_request_timestamp = None
        self.rrc_reestablishment_rejected = False
        self.mac_rach_connection_request_reason = None

    def act_on_rrc_connection_reestablishment_request(self, event):
        timestamp, _, fields = event
        if 'otherFailure' in fields['reestablishmentCause']:
            self.reestablishment_requested_on_rlf = True
            self.reestablishment_request_timestamp = timestamp
            self.last_packet_timestamp_before_rlf = fields['LastPDCPPacketTimestamp']

    def act_on_mac_rach_trigger(self, event):
        _, _, fields = event
        if fields['Reason'] == 'RLF'\
        and self.reestablishment_requested_on_rlf:
            self.mac_rach_triggered_by_rlf = True
        elif fields['Reason'] == 'CONNECTION_REQ'\
        and self.mac_rach_triggered_by_rlf:
            self.mac_rach_connection_request_reason = 'radio link failure'
        elif fields['Reason'] == 'CONNECTION_REQ'\
        and not self.mac_rach_triggered_by_rlf:
            self.mac_rach_connection_request_reason = 'connection setup'

    def act_on_mac_rach_attempt(self, event):
        _, _, fields = event
        if fields['Result'] == 'Success'\
        and (self.mac_rach_connection_request_reason == 'radio link failure'\
             or self.mac_rach_connection_request_reason == 'connection setup'):
            self.mac_rach_attempt_succeeded = True

    def act_on_rrc_serv_cell_info(self, event):
        _, _, fields = event
        self.trying_cell_dl_freq = fields['Downlink frequency']
        self.trying_cell_ul_freq = fields['Uplink frequency']
        self.trying_cell_id = fields['Cell ID']
        self.trying_cell_identity = fields['Cell Identity']

    def act_on_rrc_connection_setup(self, event):
        if self.mac_rach_attempt_succeeded:
            self.connection_setup = True

    def act_on_rrc_connection_reconfiguration(self, event):
        _, _, fields = event
        if fields['mobilityControlInfo'] == '0'\
        and self.connection_setup:
            self.rrc_reconfiguration_started = True

    def act_on_rrc_connection_reconfiguration_complete(self, event):
        timestamp, _, _ = event
        if self.rrc_reconfiguration_started:
            if self.mac_rach_connection_request_reason == 'radio link failure':
                if self.trying_cell_id == self.shared_states['last_serving_cell_id']:
                    print('Slow Recover After RLF (to prev serving cell) $ From: %s, To: %s'
                          ', Previous Cell Identity: %s, Current Cell Identity: %s'
                           % (self.reestablishment_request_timestamp, timestamp,
                              self.shared_states['last_serving_cell_identity'],
                              self.trying_cell_identity))
                else:
                    print('Slow Recover After RLF (to new cell) $ From: %s, To: %s'
                          ', Previous Cell Identity: %s, Current Cell Identity: %s'
                           % (self.reestablishment_request_timestamp, timestamp,
                              self.shared_states['last_serving_cell_identity'],
                              self.trying_cell_identity))
                self.just_switched = True
                self.shared_states['last_serving_cell_dl_freq'] = self.trying_cell_dl_freq
                self.shared_states['last_serving_cell_ul_freq'] = self.trying_cell_ul_freq
                self.shared_states['last_serving_cell_id'] = self.trying_cell_id
                self.shared_states['last_serving_cell_identity'] = self.trying_cell_identity
            elif self.mac_rach_connection_request_reason == 'connection setup':
                print('Connection Setup $')
            self.shared_states['reset_all'] = True

    def act_on_pdcp_packet(self, event):
        timestamp, _, _ = event
        if self.just_switched:
            print('Slow Recover After RLF PDCP Disruption $ From: %s, To: %s' % (self.last_packet_timestamp_before_rlf, timestamp))
            self.shared_states['reset_all'] = True
            self.just_switched = False

    def _act_on_rrc_connection_release(self, event):
        self.shared_states['reset_all'] = True

    action_to_events = {
        'rrcConnectionReestablishmentRequest' : act_on_rrc_connection_reestablishment_request,
        'LTE_MAC_Rach_Trigger' : act_on_mac_rach_trigger,
        'LTE_MAC_Rach_Attempt' : act_on_mac_rach_attempt,
        'rrcConnectionSetup' : act_on_rrc_connection_setup,
        'rrcConnectionReconfiguration' : act_on_rrc_connection_reconfiguration,
        'rrcConnectionReconfigurationComplete' : act_on_rrc_connection_reconfiguration_complete,
        'FirstPDCPPacketAfterDisruption' : act_on_pdcp_packet,
        'LTE_RRC_Serv_Cell_Info' : act_on_rrc_serv_cell_info,
        'rrcConnectionRelease' : _act_on_rrc_connection_release
    }

    def run(self, event):
        _, pkt_type, _ = event
        self.action_to_events.get(pkt_type, lambda self, event: None)(self, event)
    
    def reset(self):
        self.reset_to_normal_state()
