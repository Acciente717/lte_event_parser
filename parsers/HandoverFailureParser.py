### Copyright [2019] Zhiyao Ma
from .ParserBase import ParserBase
class HandoverFailureParser(ParserBase):
    """ The parser for detecting handover failure and recovery.

    If the following events happen in sequence, they constitute a
    handover failure and recovery.
    1. UE receives an `rrcConnectionReconfiguration` with
       `mobilityControlInfo` equals to "1".
    2. UE starts MAC random access with `Reason` field in
       `LTE_MAC_Rach_Trigger` packets equals to "HO" (handover).
    3. MAC random access aborts before succeeding.
    4. UE starts `rrcConnectionReestablishmentRequest` with
       `reestablishmentCause` as handover failure.
    5. UE starts MAC random access with `Reason` field in
       `LTE_MAC_Rach_Trigger` packets equals to "RLF" (radio link
       failure).
    6. MAC random access succeeds, i.e. the `Result` field in
       `LTE_MAC_Rach_Attempt` packets equals to `Success`.
    7. UE receives an `rrcConnectionReconfiguration` with
       `mobilityControlInfo` equals to "0".
    8. UE sends `rrcConnectionReconfigurationComplete`.

    According to the data we collected before, no PDCP data packet
    can be transmitted between the starting of the first MAC random
    access and the final `rrcConnectionReconfigurationComplete`. It
    will print a warning if the parser sees any PDCP data packet in
    between.
    """
    def __init__(self, shared_states):
        super().__init__(shared_states)
        self._reset_to_normal_state()
        self.trying_cell_dl_freq = None
        self.trying_cell_ul_freq = None
        self.trying_cell_id = None
        
        # To avoid false positive warning upon program start, set it to True.
        self.have_sent_meas_report_to_current_cell = True

    def _reset_to_normal_state(self):
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

    def _act_on_rrc_connection_reconfiguration(self, event):
        timestamp, _, fields = event

        # The first time we receive a handover command.
        if fields['mobilityControlInfo'] == '1'\
        and not self.received_handover_command:
            self.received_handover_command = True
            self.last_packet_timestamp_before_ho = fields['LastPDCPPacketTimestamp']
            self.handover_command_timestamp = timestamp
            self.target_cell_id = fields['targetPhysCellId']

        # Expected case, we are recovering from a handover failure.
        elif self.mac_rach_succeeded_after_ho_failure\
        and fields['mobilityControlInfo'] == '0':
            self.connection_reconfig_after_ho_failure = True

        # Unexpected case, we received handover commands twice
        elif fields['mobilityControlInfo'] == '1'\
        and self.received_handover_command:
            self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
            self.eprint('received handover command twice.')
        
        # Unexpected case, we received handover command but we have not sent
        # any measurement report.
        if fields['mobilityControlInfo'] == '1'\
        and not self.have_sent_meas_report_to_current_cell:
            self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
            self.eprint('received handover command but no measurement'
                        + ' report was sent.')

    def _act_on_rrc_serv_cell_info(self, event):
        _, _, fields = event

        # If we moved to a new cell, reset the flag of sending measurement report.
        if fields['Cell ID'] != self.shared_states['last_serving_cell_id']:
            self.have_sent_meas_report_to_current_cell = False

        # Check if we moved to the target cell.
        if fields['Cell ID'] == self.target_cell_id:
            self.switched_to_target_cell = True
        else:
            self.switched_to_target_cell = False
        self.trying_cell_dl_freq = fields['Downlink frequency']
        self.trying_cell_ul_freq = fields['Uplink frequency']
        self.trying_cell_id = fields['Cell ID']

    def _act_on_rrc_connection_reconfiguration_complete(self, event):
        timestamp, _, _ = event
        if self.connection_reconfig_after_ho_failure:
            # Unexpected case, the current serving cell ID does not match that
            # indicated in the previous handover command. Note that we recovered
            # from rrc connection reestablishment (cause = handover failure),
            # so it should be the same cell as indicated in the handover command.
            if not self.switched_to_target_cell:
                self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
                self.eprint('recovered from handover failure, but the current serving cell'
                            + ' is not the one indicated in the handover command.')
            print('Handover Failure $ From: %s, To: %s' % (self.handover_command_timestamp, timestamp))

            # Partially reset the states. Let `_act_on_pdcp_packet` to do the full reset
            # when it sees the first PDCP data packet afterwards.
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

    def _act_on_rrc_connection_reestablishment_request(self, event):
        timestamp, _, fields = event
        # Expected case, UE is trying to reestablish rrc connection.
        if 'handoverFailure' in fields['reestablishmentCause']\
        and self.received_handover_command:
            self.handover_failure = True
        # Expected case, the reestablishmentCause is not handoverFailure.
        elif 'handoverFailure' not in fields['reestablishmentCause']:
            self.handover_failure = False
            self.mac_rach_succeeded_after_ho_failure = False
        # Unexpected case, UE sends rrc connection reestablishment request with
        # cause handoverFailure, but no handover command was ever received.
        elif 'handoverFailure' in fields['reestablishmentCause']\
        and not self.received_handover_command:
            self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
            self.eprint('rrc connection reestablishment has cause handoverFailure,'
                        + ' but no handover command was received.')

    def _act_on_mac_rach_trigger(self, event):
        _, _, fields = event
        self.mac_rach_triggered_reason = fields['Reason']

    def _act_on_mac_rach_attempt(self, event):
        timestamp, _, fields = event
        # If the recent triggering reason of MAC RACH is RLF, and a previous
        # handover failed, and the new MAC RACH succeeded, mark it.
        if fields['Result'] == 'Success'\
        and self.handover_failure\
        and self.mac_rach_triggered_reason == 'RLF':
            self.mac_rach_succeeded_after_ho_failure = True
        # Sanity check. If the triggered reason is "HO" but we didn't receive
        # any handover command, output a warning.
        elif self.mac_rach_triggered_reason == 'HO'\
        and not self.received_handover_command:
            self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
            self.eprint('mac rach triggered by handover, but no handover command was received.')

    def _act_on_pdcp_packet(self, event):
        timestamp, _, _ = event
        if self.just_handovered:
            print('Handover Failure PDCP Disruption $ From: %s, To: %s' % (self.last_packet_timestamp_before_ho, timestamp))
            self.shared_states['reset_all'] = True

    def _act_on_meas_results(self, event):
        self.have_sent_meas_report_to_current_cell = True

    _action_to_events = {
        'measResults' : _act_on_meas_results,
        'rrcConnectionReconfiguration' : _act_on_rrc_connection_reconfiguration,
        'rrcConnectionReconfigurationComplete' : _act_on_rrc_connection_reconfiguration_complete,
        'rrcConnectionReestablishmentRequest' : _act_on_rrc_connection_reestablishment_request,
        'LTE_MAC_Rach_Trigger' : _act_on_mac_rach_trigger,
        'LTE_MAC_Rach_Attempt' : _act_on_mac_rach_attempt,
        'FirstPDCPPacketAfterDisruption' : _act_on_pdcp_packet,
        'LTE_RRC_Serv_Cell_Info' : _act_on_rrc_serv_cell_info
    }

    def run(self, event):
        """ Feed the parser with a new event.

        `event` should be a 3-element tuple, in the form
        `(timestamp, packet_type, fields)`, where the `timestamp` shows
        the happening time of the event, `packet_type` reveals the type
        of the event, and `fields` is a dictionary storing properties of
        the event.
        """
        _, pkt_type, _ = event
        self._action_to_events.get(pkt_type, lambda self, event: None)(self, event)

    def reset(self):
        """ Reset the states of the parser. """
        self._reset_to_normal_state()
