/* Mic capture worklet: forwards raw Float32 blocks (at the context's native rate) to the
   main thread, which resamples to 16 kHz int16 and batches for the websocket. */
class MutaCapture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("muta-capture", MutaCapture);
