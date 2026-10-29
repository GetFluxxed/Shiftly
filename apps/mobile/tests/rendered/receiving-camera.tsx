import React from 'react';
import { View } from 'react-native';
export const CameraView = React.forwardRef(function CameraView({ onCameraReady, style }: any, ref) {
  React.useEffect(() => { onCameraReady?.(); }, [onCameraReady]);
  React.useImperativeHandle(ref, () => ({ takePictureAsync: async () => ({ uri: 'data:image/jpeg;base64,aGVsbG8=', base64: 'aGVsbG8=' }), getAvailablePictureSizesAsync: async () => ['2048x1536'] }));
  return <View accessibilityLabel="Invoice camera preview" style={style} />;
});
export const useCameraPermissions = () => [{ granted: true }, async () => ({ granted: true })];
