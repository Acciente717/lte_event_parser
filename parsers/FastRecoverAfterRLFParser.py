### Copyright [2019] Zhiyao Ma
from .ParserBase import ParserBase
class FastRecoverAfterRLFParser(ParserBase):
    def __init__(self, shared_states):
        super().__init__(shared_states)
        self.reset_to_normal_state()
        self.have_sent_meas_report_to_current_cell = False
        self.trying_cell_dl_freq = None
        self.trying_cell_ul_freq = None
        self.trying_cell_id = None
    
    def reset_to_normal_state(self):
        self.switched_with_meas_report_sent = False
        self.reestablishment_requested_on_rlf = False
        self.mac_rach_triggered_by_rlf = False
        self.mac_rach_attempt_succeeded = False
        self.reestablishment_completed = False
        self.rrc_reconfiguration_started = False
        self.reestablishment_request_timestamp = None
        self.rrc_reestablishment_rejected = False
        self.mac_rach_switched_to_connection_request = False
        self.last_packet_timestamp_before_rlf = None
        self.just_switched = False

    def act_on_meas_results(self, event):
        self.have_sent_meas_report_to_current_cell = True

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
        elif fields['Reason'] == 'CONNECTION_REQ':
            self.mac_rach_switched_to_connection_request = True

    def act_on_mac_rach_attempt(self, event):
        _, _, fields = event
        if fields['Result'] == 'Success'\
        and self.mac_rach_triggered_by_rlf:
            self.mac_rach_attempt_succeeded = True

    def act_on_rrc_serv_cell_info(self, event):
        _, _, fields = event
        self.trying_cell_dl_freq = fields['Downlink frequency']
        self.trying_cell_ul_freq = fields['Uplink frequency']
        self.trying_cell_id = fields['Cell ID']

    def act_on_rrc_connection_reestablishment_complete(self, event):
        if self.mac_rach_attempt_succeeded:
            self.reestablishment_completed = True

    def act_on_rrc_connection_reconfiguration(self, event):
        _, _, fields = event
        if fields['mobilityControlInfo'] == '0'\
        and self.reestablishment_completed:
            self.rrc_reconfiguration_started = True

    def act_on_rrc_connection_reconfiguration_complete(self, event):
        timestamp, _, _ = event
        if self.rrc_reconfiguration_started\
        and not self.rrc_reestablishment_rejected\
        and not self.mac_rach_switched_to_connection_request:
            if self.shared_states['last_serving_cell_id'] == self.trying_cell_id:
                print('Fast Recovery After RLF (Self Reconnection) $ From: %s, To: %s' % (self.reestablishment_request_timestamp, timestamp))
            else:
                print('Fast Recovery After RLF (Psudo Handover) $ From: %s, To: %s' % (self.reestablishment_request_timestamp, timestamp))
            self.just_switched = True
            self.shared_states['last_serving_cell_dl_freq'] = self.trying_cell_dl_freq
            self.shared_states['last_serving_cell_ul_freq'] = self.trying_cell_ul_freq
            self.shared_states['last_serving_cell_id'] = self.trying_cell_id
        self.have_sent_meas_report_to_current_cell = False
        self.switched_with_meas_report_sent = False
        self.reestablishment_requested_on_rlf = False
        self.mac_rach_triggered_by_rlf = False
        self.mac_rach_attempt_succeeded = False
        self.reestablishment_completed = False
        self.rrc_reconfiguration_started = False
        self.reestablishment_request_timestamp = None
        self.rrc_reestablishment_rejected = False
        self.mac_rach_switched_to_connection_request = False
    
    def act_on_rrc_reestablishment_rejected(self, event):
        self.rrc_reestablishment_rejected = True

    def act_on_pdcp_packet(self, event):
        timestamp, _, _ = event
        if self.just_switched:
            print('Fast Recovery After RLF $ From: %s, To: %s' % (self.last_packet_timestamp_before_rlf, timestamp))
        self.reset_to_normal_state()

    action_to_events = {
        'measResults' : act_on_meas_results,
        'rrcConnectionReestablishmentRequest' : act_on_rrc_connection_reestablishment_request,
        'LTE_MAC_Rach_Trigger' : act_on_mac_rach_trigger,
        'LTE_MAC_Rach_Attempt' : act_on_mac_rach_attempt,
        'rrcConnectionReestablishmentComplete' : act_on_rrc_connection_reestablishment_complete,
        'rrcConnectionReconfiguration' : act_on_rrc_connection_reconfiguration,
        'rrcConnectionReconfigurationComplete' : act_on_rrc_connection_reconfiguration_complete,
        'FirstPDCPPacketAfterDisruption' : act_on_pdcp_packet,
        'rrcConnectionReestablishmentReject' : act_on_rrc_reestablishment_rejected,
        'LTE_RRC_Serv_Cell_Info' : act_on_rrc_serv_cell_info
    }

    def run(self, event):
        _, pkt_type, _ = event
        self.action_to_events.get(pkt_type, lambda self, event: None)(self, event)
