package com.thermalview.android;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbManager;
import android.os.Bundle;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.TextView;

import com.hoho.android.usbserial.driver.UsbSerialDriver;
import com.hoho.android.usbserial.driver.UsbSerialPort;
import com.hoho.android.usbserial.driver.UsbSerialProber;
import com.hoho.android.usbserial.util.SerialInputOutputManager;

import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity implements SerialInputOutputManager.Listener {
    private static final String ACTION_USB_PERMISSION = "com.thermalview.android.USB_PERMISSION";
    private static final int W = 32, H = 32, N = W * H, BYTES = N * 2;

    private UsbManager usbManager;
    private UsbSerialPort port;
    private SerialInputOutputManager ioManager;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    private final byte[] buf = new byte[BYTES];
    private int bufLen = 0;
    private final int[] frame = new int[N];
    private boolean haveFrame = false;

    private ImageView imageView;
    private TextView statsText;
    private Button connectBtn;
    private Bitmap bitmap;
    private Canvas canvas;

    private final BroadcastReceiver receiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (ACTION_USB_PERMISSION.equals(intent.getAction())) {
                UsbDevice device = intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
                if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false) && device != null) {
                    openDevice(device);
                }
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // Minimal programmatic UI
        android.widget.LinearLayout layout = new android.widget.LinearLayout(this);
        layout.setOrientation(android.widget.LinearLayout.VERTICAL);
        connectBtn = new Button(this);
        connectBtn.setText("Connect");
        connectBtn.setOnClickListener(v -> connect());
        layout.addView(connectBtn);
        imageView = new ImageView(this);
        imageView.setAdjustViewBounds(true);
        layout.addView(imageView, new android.widget.LinearLayout.LayoutParams(600, 600));
        statsText = new TextView(this);
        statsText.setText("disconnected");
        layout.addView(statsText);
        setContentView(layout);

        usbManager = (UsbManager) getSystemService(Context.USB_SERVICE);
        bitmap = Bitmap.createBitmap(W, H, Bitmap.Config.ARGB_8888);
        canvas = new Canvas(bitmap);
        registerReceiver(receiver, new IntentFilter(ACTION_USB_PERMISSION));
    }

    private void connect() {
        for (UsbDevice d : usbManager.getDeviceList().values()) {
            UsbSerialDriver driver = UsbSerialProber.getDefaultProber().probeDevice(d);
            if (driver == null) continue;
            UsbDeviceConnection conn = usbManager.openDevice(d);
            if (conn != null) {
                // permission already granted
                openWithDriver(driver, conn);
                return;
            }
            // request permission
            PendingIntent pi = PendingIntent.getBroadcast(this, 0, new Intent(ACTION_USB_PERMISSION), PendingIntent.FLAG_MUTABLE);
            usbManager.requestPermission(d, pi);
            return;
        }
        statsText.setText("no device found");
    }

    private void openWithDriver(UsbSerialDriver driver, UsbDeviceConnection conn) {
        try {
            port = driver.getPorts().get(0);
            port.open(conn);
            port.setParameters(115200, 8, UsbSerialPort.STOPBITS_1, UsbSerialPort.PARITY_NONE);
            port.setDTR(true);
            port.setRTS(true);
            ioManager = new SerialInputOutputManager(port, this);
            ioManager.start();
            connectBtn.setEnabled(false);
            statsText.setText("connected");
        } catch (IOException e) {
            statsText.setText("open failed: " + e.getMessage());
        }
    }

    private void openDevice(UsbDevice device) {
        UsbSerialDriver driver = UsbSerialProber.getDefaultProber().probeDevice(device);
        if (driver == null) return;
        UsbDeviceConnection conn = usbManager.openDevice(device);
        if (conn != null) openWithDriver(driver, conn);
    }

    @Override
    public void onNewData(byte[] data) {
        // accumulate
        int toCopy = Math.min(data.length, BYTES - bufLen);
        System.arraycopy(data, 0, buf, bufLen, toCopy);
        bufLen += toCopy;
        if (bufLen >= BYTES) {
            // decode frame
            for (int i = 0; i < N; i++) {
                int raw = (buf[i * 2 + 1] & 0xFF) << 8 | (buf[i * 2] & 0xFF);
                frame[i] = raw;
            }
            bufLen = 0;
            runOnUiThread(this::renderFrame);
        }
    }

    @Override
    public void onRunError(Exception e) {
        runOnUiThread(() -> statsText.setText("error: " + e.getMessage()));
    }

    private void renderFrame() {
        // compute stats
        int mn = Integer.MAX_VALUE, mx = Integer.MIN_VALUE;
        long sum = 0;
        for (int v : frame) { mn = Math.min(mn, v); mx = Math.max(mx, v); sum += v; }
        float minC = mn / 10f, maxC = mx / 10f, meanC = (sum / N) / 10f;
        statsText.setText(String.format("min %.1f max %.1f mean %.1f", minC, maxC, meanC));

        // render with iron_red palette (simple)
        float vmin = minC, vmax = maxC;
        if (vmax - vmin < 6) vmax = vmin + 6;
        for (int i = 0; i < N; i++) {
            float t = (frame[i] / 10f - vmin) / (vmax - vmin);
            t = Math.max(0, Math.min(1, t));
            int r, g, b;
            if (t <= 0.5) { r = (int)(t * 180); g = 0; b = (int)(t * 120); }
            else if (t <= 0.8) { r = 255; g = (int)(t * 255); b = 0; }
            else { r = 255; g = 253; b = 238; }
            int x = i % W, y = i / W;
            bitmap.setPixel(x, y, Color.rgb(r, g, b));
        }
        imageView.setImageBitmap(bitmap);
        imageView.invalidate();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (ioManager != null) ioManager.stop();
        if (port != null) try { port.close(); } catch (IOException ignored) {}
        unregisterReceiver(receiver);
    }
}
