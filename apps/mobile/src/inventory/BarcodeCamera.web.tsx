import React from 'react';

import { Body, Button, Card, Heading } from '@/src/ui/components';

type Props = {
  onScan: (result: { data: string; type: string }) => void;
  onClose: () => void;
};

export function BarcodeCamera({ onClose }: Props) {
  return <Card>
    <Heading>Barcode camera</Heading>
    <Body muted>Enter the barcode here, or scan it in the mobile app.</Body>
    <Button title="Enter code instead" onPress={onClose} />
  </Card>;
}
