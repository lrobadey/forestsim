import { useEffect, useState } from "react";
import { createForestPrototypeState, dominantStatusText, resetForestState, setPlaybackSpeed, setPlaybackState, stepForestState, updateForestControls } from "./sim";
import type { ForestControls, PlaybackSpeed } from "./types";

const SPEED_INTERVALS: Record<PlaybackSpeed, number> = {
  "0.5x": 1400,
  "1x": 800,
  "2x": 400,
  "4x": 200,
  "10x": 80,
  "20x": 40,
};

export function useForestPrototype() {
  const [state, setState] = useState(() => createForestPrototypeState());

  useEffect(() => {
    if (!state.isPlaying) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setState((current) => stepForestState(current));
    }, SPEED_INTERVALS[state.speed]);

    return () => window.clearInterval(intervalId);
  }, [state.isPlaying, state.speed]);

  const setControl = (control: keyof ForestControls, value: number) => {
    setState((current) => updateForestControls(current, { [control]: value }));
  };

  return {
    state,
    statusText: dominantStatusText(state),
    play: () => setState((current) => setPlaybackState(current, true)),
    pause: () => setState((current) => setPlaybackState(current, false)),
    reset: () => setState((current) => resetForestState(current)),
    step: () => setState((current) => stepForestState(current)),
    setControl,
    setSpeed: (speed: PlaybackSpeed) => setState((current) => setPlaybackSpeed(current, speed)),
  };
}
