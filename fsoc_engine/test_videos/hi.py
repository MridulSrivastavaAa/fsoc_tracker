import cv2
import numpy as np
import pandas as pd

def render_beacon_video(csv_path="telemetry_26169.csv", output_path="beacon_video_26169.mp4"):
    df = pd.read_csv(csv_path)
    
    width, height = 640, 480
    fps = 60
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    trail = []
    trail_length = 90  # ~1.5 seconds of historical breadcrumbs

    for idx, row in df.iterrows():
        # Initialize dark night-vision / tactical FLIR sensor canvas
        frame = np.full((height, width, 3), (18, 22, 26), dtype=np.uint8)
        
        # Draw background reticle & subtle coordinate grid
        for gx in range(80, width, 80):
            cv2.line(frame, (gx, 0), (gx, height), (30, 36, 42), 1)
        for gy in range(60, height, 60):
            cv2.line(frame, (0, gy), (width, gy), (30, 36, 42), 1)
            
        cv2.circle(frame, (width // 2, height // 2), 4, (55, 65, 75), -1)
        
        tx = int(round(row["truth_x"]))
        ty = int(round(row["truth_y"]))
        trail.append((tx, ty))
        if len(trail) > trail_length:
            trail.pop(0)
            
        # Draw fading trajectory trail
        for i in range(1, len(trail)):
            alpha = i / len(trail)
            color = (int(40 * alpha), int(180 * alpha), int(255 * alpha))
            thickness = 1 if i < trail_length // 2 else 2
            cv2.line(frame, trail[i - 1], trail[i], color, thickness)
            
        # Draw beacon target (pulsing glow, inner core, optical tracking brackets)
        cv2.circle(frame, (tx, ty), 16, (0, 140, 255), 1, cv2.LINE_AA)
        cv2.circle(frame, (tx, ty), 6, (0, 215, 255), -1, cv2.LINE_AA)
        cv2.circle(frame, (tx, ty), 2, (255, 255, 255), -1, cv2.LINE_AA)
        
        # Reticle crosshairs
        cv2.line(frame, (tx - 22, ty), (tx - 10, ty), (0, 255, 200), 1)
        cv2.line(frame, (tx + 10, ty), (tx + 22, ty), (0, 255, 200), 1)
        cv2.line(frame, (tx, ty - 22), (tx, ty - 10), (0, 255, 200), 1)
        cv2.line(frame, (tx, ty + 10), (tx, ty + 22), (0, 255, 200), 1)
        
        # HUD Telemetry Overlay
        hud_color = (0, 255, 170)
        cv2.putText(frame, f"BEACON ID: 26169", (20, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, hud_color, 1, cv2.LINE_AA)
        cv2.putText(frame, f"FRAME: {int(row['frame']):04d} / 1200", (20, 52), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(frame, f"TIME: {row['time_s']:.2f}s", (20, 72), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(frame, f"TRUTH (X,Y): ({row['truth_x']:.2f}, {row['truth_y']:.2f})", (20, 92), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
        cv2.putText(frame, f"STATUS: {row['phase'].upper()}", (20, 112), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 100), 1, cv2.LINE_AA)
        
        out.write(frame)
        
    out.release()
    print(f"Render complete: {output_path} (1200 frames @ 60 FPS)")

if __name__ == "__main__":
    render_beacon_video()