### Copyright [2019] Zhiyao Ma
from .ParserBase import ParserBase
class HandoverSuccessParser(ParserBase):
    def __init__(self, shared_states):
        super().__init__(shared_states)
        self.reset_to_normal_state()

    def reset_to_normal_state(self):
        self.handover_command_timestamp = None
        self.target_cell_id = None
        self.received_handover_command = False
        self.mac_rach_triggered_reason = None
        self.mac_rach_just_succeeded = False
        self.last_packet_timestamp_before_ho = None
        self.just_handovered = False

    def act_on_rrc_connection_reconfiguration(self, event):
        timestamp, _, fields = event
        if fields['mobilityControlInfo'] == '1':
            self.received_handover_command = True
            self.last_packet_timestamp_before_ho = fields['LastPDCPPacketTimestamp']
            self.handover_command_timestamp = timestamp
            self.target_cell_id = fields['targetPhysCellId']

    def act_on_mac_rach_trigger(self, event):
        _, _, fields = event
        self.mac_rach_triggered_reason = fields['Reason']

    def act_on_mac_rach_attempt(self, event):
        _, _, fields = event
        if fields['Result'] == 'Success':
            if self.received_handover_command\
            and self.mac_rach_triggered_reason == 'HO':
                self.mac_rach_just_succeeded = True

    def act_on_rrc_serv_cell_info(self, event):
        timestamp, _, fields = event
        if fields['Cell ID'] == self.target_cell_id\
        and self.mac_rach_just_succeeded:
            print('Handover Success $ From: %s, To: %s' % (self.handover_command_timestamp, timestamp), end='')
            if self.shared_states['last_serving_cell_dl_freq'] is None\
            or self.shared_states['last_serving_cell_ul_freq'] is None:
                print(', Frequecy Change: unknown')
            elif self.shared_states['last_serving_cell_dl_freq'] == fields['Downlink frequency']\
            and self.shared_states['last_serving_cell_ul_freq'] == fields['Uplink frequency']:
                print(', Frequecy Change: intra')
            else:
                print(', Frequecy Change: inter')

            self.handover_command_timestamp = None
            self.target_cell_id = None
            self.received_handover_command = False
            self.mac_rach_triggered_reason = None
            self.mac_rach_just_succeeded = False
            self.just_handovered = True
            self.shared_states['last_serving_cell_dl_freq'] = fields['Downlink frequency']
            self.shared_states['last_serving_cell_ul_freq'] = fields['Uplink frequency']
            self.shared_states['last_serving_cell_id'] = fields['Cell ID']

    def act_on_pdcp_packet(self, event):
        timestamp, _, _ = event
        if self.just_handovered:
            print('Handover Success PDCP Disruption $ From: %s, To: %s' % (self.last_packet_timestamp_before_ho, timestamp))
        self.reset_to_normal_state()

    action_to_events = {
        'rrcConnectionReconfiguration' : act_on_rrc_connection_reconfiguration,
        'LTE_MAC_Rach_Trigger' : act_on_mac_rach_trigger,
        'LTE_MAC_Rach_Attempt' : act_on_mac_rach_attempt,
        'FirstPDCPPacketAfterDisruption' : act_on_pdcp_packet,
        'LTE_RRC_Serv_Cell_Info' : act_on_rrc_serv_cell_info
    }

    def run(self, event):
        _, pkt_type, _ = event
        self.action_to_events.get(pkt_type, lambda self, event: None)(self, event)
