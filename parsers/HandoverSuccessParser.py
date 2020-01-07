### Copyright [2019] Zhiyao Ma
from .ParserBase import ParserBase
class HandoverSuccessParser(ParserBase):
    """ The parser for detecting successful handover.

    If the following events happen in sequence, they constitute a
    successful handover.
    1. UE receives an `rrcConnectionReconfiguration` with
       `mobilityControlInfo` equals to "1".
    2. UE starts MAC random access with `Reason` field in
       `LTE_MAC_Rach_Trigger` packets equals to "HO" (handover).
    3. MAC random access succeeds, i.e. the `Result` field in
       `LTE_MAC_Rach_Attempt` packets equals to `Success` before
       any new `LTE_MAC_Rach_Trigger` with other reasons (very likely
       to be RLF (radio link failure)).

    The data transfer resumes immediately after the successful MAC random
    access with triggring reason `HO`. However, to decide whether the handover
    is inter- or intra-frequency, we must wait until we see an
    `LTE_RRC_Serv_Cell_Info` packet, which appears a short while after.
    We defer output of the handover summary report after seeing that.

    Note that UE can still receive PDCP data packet even after receiving
    the handover command, i.e. `rrcConnectionReconfiguration` with
    `mobilityControlInfo` equals to "1". If so, we should update the
    `last_packet_timestamp_before_ho`.
    """

    def __init__(self, shared_states):
        super().__init__(shared_states)
        self._reset_to_normal_state()

        self.last_packet_timestamp_before_ho = None
        self.just_handovered = False

        # To avoid false positive warning upon program start, set it to True.
        self.have_sent_meas_report_to_current_cell = True

    def _reset_to_normal_state(self):
        self.handover_command_timestamp = None
        self.target_cell_id = None
        self.received_handover_command = False
        self.mac_rach_triggered_reason = None
        self.mac_rach_just_succeeded = False
        self.mac_rach_success_timestamp = None
        self.first_packet_timestamp_after_ho = None

    def _act_on_rrc_connection_reconfiguration(self, event):
        timestamp, _, fields = event

        # If we see the handover command, log the timestamp of the last PDCP
        # packet received before the command, the timestamp of this command,
        # and target cell ID.
        if fields['mobilityControlInfo'] == '1'\
        and not self.received_handover_command:
            self.received_handover_command = True
            self.handover_command_timestamp = timestamp
            self.target_cell_id = fields['targetPhysCellId']
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

    def _act_on_mac_rach_trigger(self, event):
        timestamp, _, fields = event
        
        # Expected case, MAC RACH is triggered by handover.
        if fields['Reason'] == 'HO':
            self.mac_rach_triggered_reason = 'HO'
            self.last_packet_timestamp_before_ho = fields['LastPDCPPacketTimestamp']
        # Expected case, MAC RACH was once triggered by handover and
        # succeeded, but before we received any cell information packet,
        # another new MAC RACH was triggered. We must report the handover
        # now, and leave the intra/inter field as unknown. Only reset
        # this parser, because other parsers might be in the middle of
        # detecting an event.
        elif fields['Reason'] != 'HO'\
        and fields['Reason'] != 'UL_DATA'\
        and fields['Reason'] != 'DL_DATA'\
        and self.mac_rach_just_succeeded:
            print('Handover Success $ From: %s, To: %s, Frequecy Change: unknown'
                  % (self.handover_command_timestamp, self.mac_rach_success_timestamp))
            self._reset_to_normal_state()

        # Unexpected case. If the triggered reason is "HO" but we didn't receive
        # any handover command, output a warning.
        if fields['Reason'] == 'HO'\
        and not self.received_handover_command:
            self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
            self.eprint('mac rach triggered by handover, but no handover command was received.')

    def _act_on_mac_rach_attempt(self, event):
        timestamp, _, fields = event
        # If the recent triggering reason of MAC RACH is HO (handover),
        # and we have received handover request, and the result is success,
        # mark it.
        if fields['Result'] == 'Success'\
        and self.received_handover_command\
        and self.mac_rach_triggered_reason == 'HO':
            self.mac_rach_just_succeeded = True
            self.mac_rach_success_timestamp = timestamp

    def _act_on_rrc_serv_cell_info(self, event):
        timestamp, _, fields = event

        # If we moved to a new cell, reset the flag of sending measurement report.
        if fields['Cell ID'] != self.shared_states['last_serving_cell_id']:
            self.have_sent_meas_report_to_current_cell = False

        # If the the MAC RACH triggered by handover is succeeded, and the
        # target cell ID matches that indicated in the handover command,
        # we print the handover summary.
        if fields['Cell ID'] == self.target_cell_id\
        and self.mac_rach_just_succeeded:
            print('Handover Success $ From: %s, To: %s'
                  % (self.handover_command_timestamp, self.mac_rach_success_timestamp), end='')

            # Decide whether the handover is inter- or intra-frequency.
            if self.shared_states['last_serving_cell_dl_freq'] is None\
            or self.shared_states['last_serving_cell_ul_freq'] is None:
                print(', Frequecy Change: unknown, Previous Cell Identity:',
                      self.shared_states['last_serving_cell_identity'])
            elif self.shared_states['last_serving_cell_dl_freq'] == fields['Downlink frequency']\
            and self.shared_states['last_serving_cell_ul_freq'] == fields['Uplink frequency']:
                print(', Frequecy Change: intra, Previous Cell Identity:',
                      self.shared_states['last_serving_cell_identity'])
            else:
                print(', Frequecy Change: inter, Previous Cell Identity:',
                      self.shared_states['last_serving_cell_identity'])

            # Reset the states.
            self.shared_states['reset_all'] = True

            self.just_handovered = True

            # Update shared states.
            self.shared_states['last_serving_cell_dl_freq'] = fields['Downlink frequency']
            self.shared_states['last_serving_cell_ul_freq'] = fields['Uplink frequency']
            self.shared_states['last_serving_cell_id'] = fields['Cell ID']
            self.shared_states['last_serving_cell_identity'] = fields['Cell Identity']

            # If we have already received PDCP data packets after handover,
            # output the PDCP disruption summary and then reset all states.
            # Otherwise, wait for the first PDCP data packet and defer the
            # output to `_act_on_pdcp_packet`.
            if self.first_packet_timestamp_after_ho is not None\
            and self.just_handovered:
                print('Handover Success PDCP Disruption $ From: %s, To: %s'
                      % (self.last_packet_timestamp_before_ho,
                         self.first_packet_timestamp_after_ho))
                self.just_handovered = False
                self.first_packet_timestamp_after_ho = None

        # Sanity check. If the cell ID indicated in the handover command
        # does not match the new serving cell ID, output a warning.
        elif self.mac_rach_just_succeeded\
        and fields['Cell ID'] != self.target_cell_id:
            self.eprint('Warning [%s] [%s]: '
                        % (self.__class__.__name__, timestamp), end='')
            self.eprint('handover succeeded, but the target cell is not the one indicated in the handover command.')

    def _act_on_pdcp_packet(self, event):
        timestamp, _, _ = event

        # If this is the first PDCP data packet we see after handover and
        # we have already printed the handover summary, output the PDCP
        # disruption summary and then reset the states.
        if self.just_handovered:
            print('Handover Success PDCP Disruption $ From: %s, To: %s'
                  % (self.last_packet_timestamp_before_ho, timestamp))
            self.shared_states['reset_all'] = True
            self.just_handovered = False
        # If this is the first PDCP data packet we see after handover,
        # but we are still waiting for an `LTE_RRC_Serv_Cell_Info` packet,
        # log the timestamp and print it later (in
        # _act_on_rrc_serv_cell_info).
        elif self.mac_rach_just_succeeded\
        and self.first_packet_timestamp_after_ho is None:
            self.first_packet_timestamp_after_ho = timestamp
        # If we have already received handover command, but we still receive
        # more PDCP data packets, update timestamp of the last packet before
        # handover, i.e. not using that in the handover command.
        elif self.received_handover_command\
        and self.mac_rach_triggered_reason is None:
            self.last_packet_timestamp_before_ho = timestamp

    def _act_on_meas_results(self, event):
        self.have_sent_meas_report_to_current_cell = True

    def _act_on_rrc_connection_release(self, event):
        self.shared_states['reset_all'] = True

    _action_to_events = {
        'measResults' : _act_on_meas_results,
        'rrcConnectionReconfiguration' : _act_on_rrc_connection_reconfiguration,
        'LTE_MAC_Rach_Trigger' : _act_on_mac_rach_trigger,
        'LTE_MAC_Rach_Attempt' : _act_on_mac_rach_attempt,
        'FirstPDCPPacketAfterDisruption' : _act_on_pdcp_packet,
        'LTE_RRC_Serv_Cell_Info' : _act_on_rrc_serv_cell_info,
        'rrcConnectionRelease' : _act_on_rrc_connection_release
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

        # Only take actions to those packets that are listed in
        # `_action_to_events`.
        self._action_to_events.get(pkt_type, lambda self, event: None)(self, event)

    def reset(self):
        """ Reset the states of the parser. """
        self._reset_to_normal_state()
