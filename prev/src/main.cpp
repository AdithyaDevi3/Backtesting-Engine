#include <iostream>
#include "DataHandler.hpp"

int main() {
    std::cout << "Backtest starting\n";

    DataHandler data;

    while (data.hasNext()) {
        Bar bar = data.getNext();
        std::cout << bar.date << " | " << bar.clos << "\n";
    }

    std::cout << "Backtest finished\n";
    return 0;
}
