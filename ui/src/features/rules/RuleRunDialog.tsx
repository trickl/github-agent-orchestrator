import React from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';

export function RuleRunDialog(props: {
  open: boolean;
  ruleName: string;
  onConfirm: () => void;
  onCancel: () => void;
}): React.JSX.Element {
  return (
    <ConfirmDialog
      open={props.open}
      title="Run rule now?"
      body={`Run “${props.ruleName}”? This will create a pending issue.`}
      confirmLabel="Run now"
      onConfirm={props.onConfirm}
      onCancel={props.onCancel}
    />
  );
}
