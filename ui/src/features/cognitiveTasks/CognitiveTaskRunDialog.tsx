import React from 'react';
import { ConfirmDialog } from '../../components/ConfirmDialog';

export function CognitiveTaskRunDialog(props: {
  open: boolean;
  taskName: string;
  onConfirm: () => void;
  onCancel: () => void;
}): React.JSX.Element {
  return (
    <ConfirmDialog
      open={props.open}
      title="Run cognitive task now?"
      body={`Run “${props.taskName}”? This will create a pending issue.`}
      confirmLabel="Run now"
      onConfirm={props.onConfirm}
      onCancel={props.onCancel}
    />
  );
}
