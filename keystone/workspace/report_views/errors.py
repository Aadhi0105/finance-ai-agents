"""Safe public errors for the native-report read boundary."""

ERRORS = {
    'native_view_unavailable': (409, 'This saved run has no registered native report view.', False),
    'unsupported_report_schema': (409, 'This native report or source version is unsupported.', False),
    'saved_evidence_invalid': (503, 'Saved report evidence is missing, changed or invalid.', False),
    'saved_run_not_found': (404, 'The requested saved run is not registered.', False),
    'local_access_required': (403, 'Local same-origin access is required.', False),
    'read_only_workspace': (405, 'This workspace is read-only.', False),
}


class NativeViewError(ValueError):
    def __init__(self, code='saved_evidence_invalid'):
        self.code = code
        self.status, self.message, self.retryable = ERRORS[code]
        super().__init__(self.message)

    def envelope(self):
        return {'error': {'code': self.code, 'message': self.message,
                          'retryable': self.retryable}}
