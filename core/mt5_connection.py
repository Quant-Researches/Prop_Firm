import MetaTrader5 as mt5
import logging

logger = logging.getLogger("MT5Connection")

class MT5Connection:
    @staticmethod
    def connect(account, password, server, path=""):
        """
        Initializes MetaTrader 5 and logs in with the given credentials.
        Returns True if successful, False otherwise.
        """
        init_kwargs = {}
        if path:
            init_kwargs["path"] = path
            
        if account and password and server:
            init_kwargs["login"] = int(account)
            init_kwargs["password"] = password
            init_kwargs["server"] = server
            
        if not mt5.initialize(**init_kwargs):
            err = mt5.last_error()
            logger.error(f"Failed to initialize MT5: {err}")
            return False
                
        return True

    @staticmethod
    def shutdown():
        """
        Shuts down the MT5 connection.
        """
        mt5.shutdown()
