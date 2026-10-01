import React from 'react';

import { Body, Button, Card, Heading } from '@/src/ui/components';

type Props = {
  onScan: (result: { data: string; type: string }) => void;
  onClose: () => void;
};

export function BarcodeCamera({ onClose }: Props) {
  return <Card>
    <Heading>Barcode camera</Heading>
    <Body muted>Camera scanning is available in the Shiftly mobile app. Enter the barcode to continue in your browser.</Body>
    <Button title="Enter code instead" onPress={onClose} />
  </Card>;
}
