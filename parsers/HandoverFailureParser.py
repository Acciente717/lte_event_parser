### Copyright [2019] Zhiyao Ma
from .ParserBase import ParserBase
class HandoverFailureParser(ParserBase):
    def __init__(self, shared_states):
        super().__init__(shared_states)
        self.reset_to_normal_state()
        self.trying_cell_dl_freq = None
        self.trying_cell_ul_freq = None
        self.trying_cell_id = None

    def reset_to_normal_state(self):
        self.handover_command_timestamp = None
        self.target_cell_id = None
        self.received_handover_command = False
        self.mac_rach_triggered_reason = None
        self.handover_failure = False
        self.mac_rach_succeeded_after_ho_failure = False
        self.connection_reconfig_after_ho_failure = False
        self.switched_to_target_cell = False
        self.last_packet_timestamp_before_ho = None
        self.just_handovered = False

    def act_on_rrc_connection_reconfiguration(self, event):
        timestamp, _, fields = event
        if fields['mobilityControlInfo'] == '1':
            self.received_handover_command = True
            self.last_packet_timestamp_before_ho = fields['LastPDCPPacketTimestamp']
            self.handover_command_timestamp = timestamp
            self.target_cell_id = fields['targetPhysCellId']
        else:
            if self.mac_rach_succeeded_after_ho_failure:
                self.connection_reconfig_after_ho_failure = True

    def act_on_rrc_serv_cell_info(self, event):
        _, _, fields = event
        if fields['Cell ID'] == self.target_cell_id:
            self.switched_to_target_cell = True
            self.trying_cell_dl_freq = fields['Downlink frequency']
            self.trying_cell_ul_freq = fields['Uplink frequency']
            self.trying_cell_id = fields['Cell ID']

    def act_on_rrc_connection_reconfiguration_complete(self, event):
        timestamp, _, _ = event
        if self.connection_reconfig_after_ho_failure\
        and self.switched_to_target_cell:
            print('Handover Failure $ From: %s, To: %s' % (self.handover_command_timestamp, timestamp))
            self.handover_command_timestamp = None
            self.target_cell_id = None
            self.received_handover_command = False
            self.mac_rach_triggered_reason = None
            self.handover_failure = False
            self.mac_rach_succeeded_after_ho_failure = False
            self.connection_reconfig_after_ho_failure = False
            self.switched_to_target_cell = False
            self.just_handovered = True
            self.shared_states['last_serving_cell_dl_freq'] = self.trying_cell_dl_freq
            self.shared_states['last_serving_cell_ul_freq'] = self.trying_cell_ul_freq
            self.shared_states['last_serving_cell_id'] = self.trying_cell_id

    def act_on_rrc_connection_reestablishment_request(self, event):
        _, _, fields = event
        if 'handoverFailure' in fields['reestablishmentCause']:
            self.handover_failure = True

    def act_on_mac_rach_trigger(self, event):
        _, _, fields = event
        self.mac_rach_triggered_reason = fields['Reason']

    def act_on_mac_rach_attempt(self, event):
        _, _, fields = event
        if fields['Result'] == 'Success':
            if self.handover_failure\
            and self.mac_rach_triggered_reason == 'RLF':
                self.mac_rach_succeeded_after_ho_failure = True

    def act_on_pdcp_packet(self, event):
        timestamp, _, _ = event
        if self.just_handovered:
            print('Handover Failure PDCP Disruption $ From: %s, To: %s' % (self.last_packet_timestamp_before_ho, timestamp))
        self.reset_to_normal_state()

    action_to_events = {
        'rrcConnectionReconfiguration' : act_on_rrc_connection_reconfiguration,
        'rrcConnectionReconfigurationComplete' : act_on_rrc_connection_reconfiguration_complete,
        'rrcConnectionReestablishmentRequest' : act_on_rrc_connection_reestablishment_request,
        'LTE_MAC_Rach_Trigger' : act_on_mac_rach_trigger,
        'LTE_MAC_Rach_Attempt' : act_on_mac_rach_attempt,
        'FirstPDCPPacketAfterDisruption' : act_on_pdcp_packet,
        'LTE_RRC_Serv_Cell_Info' : act_on_rrc_serv_cell_info
    }

    def run(self, event):
        _, pkt_type, _ = event
        self.action_to_events.get(pkt_type, lambda self, event: None)(self, event)
