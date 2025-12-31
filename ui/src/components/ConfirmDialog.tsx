import React from 'react';
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material';

export function ConfirmDialog(props: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}): React.JSX.Element {
  return (
    <Dialog open={props.open} onClose={props.onCancel} maxWidth="sm" fullWidth>
      <DialogTitle>{props.title}</DialogTitle>
      <DialogContent>
        <DialogContentText>{props.body}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={props.onCancel}>{props.cancelLabel ?? 'Cancel'}</Button>
        <Button
          onClick={props.onConfirm}
          variant="contained"
          color={props.destructive ? 'error' : 'primary'}
        >
          {props.confirmLabel ?? 'Confirm'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
