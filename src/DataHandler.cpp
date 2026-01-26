#include "DataHandler.hpp"

DataHandler::DataHandler() : index(0){
    data.push_back({"2020-01-01", 100.0});
    data.push_back({"2020-01-02", 101.5});
    data.push_back({"2020-01-03", 99.0});
}
bool DataHandler::hasNext() const {
    return index < data.size();
}

Bar DataHandler::getNext() {
    return data[index++];
}