package com.waveguard.telephony;

import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ResultReceiver;
import java.lang.reflect.Method;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class UssdNativeRunner {
    public static void main(String[] args) {
        String code = args.length > 0 ? args[0] : "*9113#";
        int timeoutSec = args.length > 1 ? Integer.parseInt(args[1]) : 15;

        try {
            if (Looper.myLooper() == null) {
                Looper.prepareMainLooper();
            }

            Class<?> sm = Class.forName("android.os.ServiceManager");
            Method getService = sm.getMethod("getService", String.class);

            // SubId
            IBinder isubBinder = (IBinder) getService.invoke(null, "isub");
            Class<?> iSubStub = Class.forName("com.android.internal.telephony.ISub$Stub");
            Method asInterfaceSub = iSubStub.getMethod("asInterface", IBinder.class);
            Object iSub = asInterfaceSub.invoke(null, isubBinder);
            Method getDefaultSubId = iSub.getClass().getMethod("getDefaultSubId");
            int subId = (int) getDefaultSubId.invoke(iSub);

            // ITelephony
            IBinder phoneBinder = (IBinder) getService.invoke(null, "phone");
            Class<?> iTelephonyStub = Class.forName("com.android.internal.telephony.ITelephony$Stub");
            Method asInterfacePhone = iTelephonyStub.getMethod("asInterface", IBinder.class);
            Object iTelephony = asInterfacePhone.invoke(null, phoneBinder);

            final CountDownLatch latch = new CountDownLatch(1);
            final Handler handler = new Handler(Looper.getMainLooper());
            final StringBuilder reponseFinale = new StringBuilder();
            final int[] codeStatut = new int[]{-1};

            ResultReceiver receiver = new ResultReceiver(handler) {
                @Override
                protected void onReceiveResult(int resultCode, Bundle resultData) {
                    codeStatut[0] = resultCode;
                    if (resultData != null) {
                        for (String key : resultData.keySet()) {
                            Object val = resultData.get(key);
                            if (val != null) {
                                try {
                                    Method getReturnMsg = val.getClass().getMethod("getReturnMessage");
                                    Object msg = getReturnMsg.invoke(val);
                                    if (msg != null) {
                                        reponseFinale.append(msg.toString());
                                    }
                                } catch (Exception e) {
                                    reponseFinale.append(val.toString());
                                }
                            }
                        }
                    }
                    latch.countDown();
                }
            };

            Method handleUssd = iTelephony.getClass().getMethod("handleUssdRequest", int.class, String.class, ResultReceiver.class);
            handleUssd.invoke(iTelephony, subId, code, receiver);

            new Thread(() -> {
                try {
                    boolean ok = latch.await(timeoutSec, TimeUnit.SECONDS);
                    if (!ok) {
                        System.out.println("{\"success\":false,\"error\":\"TIMEOUT_USSD\"}");
                        System.exit(1);
                    }
                    
                    String texte = reponseFinale.toString().trim();
                    // Extraire le solde numerique : 'Solde Wave: 32F' -> 32.0
                    Double solde = null;
                    Pattern p = Pattern.compile("(?i)solde[^:]*:\\s*([0-9\\s]+)\\s*F");
                    Matcher m = p.matcher(texte);
                    if (m.find()) {
                        String brut = m.group(1).replaceAll("\\s+", "");
                        try {
                            solde = Double.parseDouble(brut);
                        } catch (Exception ex) {}
                    }

                    // Echapper pour JSON
                    String escaped = texte.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "");
                    System.out.println("{"
                        + "\"success\":true,"
                        + "\"status_code\":" + codeStatut[0] + ","
                        + "\"balance\":" + (solde != null ? solde : "null") + ","
                        + "\"currency\":\"FCFA\","
                        + "\"raw\":\"" + escaped + "\""
                        + "}");
                    System.exit(0);
                } catch (Exception e) {
                    System.out.println("{\"success\":false,\"error\":\"" + e.getMessage() + "\"}");
                    System.exit(1);
                }
            }).start();

            Looper.loop();

        } catch (Throwable t) {
            System.out.println("{\"success\":false,\"error\":\"" + t.getMessage() + "\"}");
            System.exit(1);
        }
    }
}
